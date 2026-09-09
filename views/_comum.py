"""Andaime compartilhado pelas quatro paginas de numeros (o Guia nao usa).

Nao e uma pagina: e o que as paginas repetiriam se este arquivo nao existisse --
leitura do estado de filtros, carregamento paralelo das metricas, a faixa de
KPIs e os utilitarios de grafico.

Regras que este modulo faz valer:

* **zero SQL**: tudo vem de ``frotas.metrics.*``;
* **zero hex literal**: cor so via ``frotas.ui.theme``;
* **zero limiar**: ambar/vermelho de cada KPI sao lidos das colunas
  ``limiar_ambar``/``limiar_vermelho`` de ``alertas.avaliar()``;
* **zero nome de coluna na tela**: todo cabecalho passa por
  ``frotas.ui.rotulos`` -- inclusive o expander "ver dados", que antes despejava
  o DataFrame cru;
* **teto de linhas**: nenhuma chamada aqui devolve mais de ~1.000 linhas
  (o pooler entrega ~200 linhas/s com 9-10 colunas).

Densidade
---------
A critica do dono foi "texto demais competindo com os numeros". Por isso
:func:`mostrar_grafico` recebe ``nota`` -- **nota de rodape do visual**, curta e
so quando o numero nao se interpreta sozinho -- e nao mais um paragrafo
descrevendo o que o grafico ja mostra.

Carregamento em paralelo
------------------------
A restricao que manda no desenho e a latencia por consulta (~490 ms de piso) e
nao o servidor. ``comparativo_por_segmento`` sozinho custa ~13 s a frio. Por
isso as chamadas independentes de cada pagina vao juntas para um
``ThreadPoolExecutor`` de 5 trabalhadores (o pool do engine tem 3+2 = 5
conexoes), com o ``ScriptRunContext`` propagado para as threads.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping, Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frotas import config, leitura as ia
from frotas.filtros import Filtros
from frotas.metrics import alertas as m_alertas
from frotas.ui import componentes as ui
from frotas.ui import format as fmt
from frotas.ui import rotulos as rot
from frotas.ui import theme
from frotas.ui.theme import Tema

#: Caminhos de URL das paginas -- usados nos links de acao dos alertas.
ROTAS: Mapping[int, str] = {
    0: "/guia",
    1: "/metas",
    2: "/faturamento-recebimento",
    3: "/inadimplencia",
    4: "/custos",
}

#: Que filtros cada pagina exibe, e portanto quais chips o cabecalho mostra.
#: So entram os que **mudam o numero daquela analise**: um filtro visivel que nao
#: faz nada e pior que filtro nenhum, porque o usuario mexe nele e conclui que o
#: dashboard esta quebrado. Fonte: ``frotas.filtros.politica_filtros()``.
#:
#: * Metas nao lista porte, rating, tipo de contrato nem cliente: a tabela de
#:   orcamento so tem os niveis Empresa e Segmento.
#: * Inadimplencia nao lista periodo: a pagina e uma leitura numa data, e uma
#:   fatura de 2024 ainda vencida conta nela.
FILTROS_DA_PAGINA: Mapping[int, tuple[str, ...]] = {
    0: (),
    # Metas usa "ano", nao "periodo": tudo na pagina e por exercicio (a meta e
    # anual, a serie mensal cobre os 12 meses do ano, a matriz compara ano a ano).
    # Com o filtro de periodo, trocar "Ultimos 12 meses" por "Todo o periodo"
    # mantinha 2026 nos dois casos e nada mudava na tela -- parecia quebrado.
    1: ("ano", "granularidade", "segmento"),
    2: ("periodo", "granularidade", "data", "segmento", "porte", "rating", "tipo_contrato",
        "cliente"),
    3: ("data", "segmento", "porte", "rating", "tipo_contrato", "cliente"),
    # Custos nao lista "data": os numeros da pagina sao todos por competencia, e a
    # data so mexia na avaliacao dos alertas de ociosidade. Um filtro cujo unico
    # efeito visivel e mudar a cor de um alerta confunde mais do que serve.
    4: ("periodo", "granularidade", "segmento", "porte", "rating", "tipo_contrato", "cliente"),
}

#: url_path -> numero da pagina. "" porque o Streamlit serve a default na raiz.
PAGINA_POR_URL: Mapping[str, int] = {
    "": 0, "guia": 0, "metas": 1, "faturamento-recebimento": 2,
    "inadimplencia": 3, "custos": 4,
}

#: Alertas em escopo por pagina. ``0`` = qualidade de dado (A18, A19), que
#: aparece em todas via :func:`barra_qualidade`. Sao 13 regras no total; as
#: outras 7 sairam com o escopo (margem, serie de inadimplencia, corretiva).
ALERTAS_DA_PAGINA: Mapping[int, tuple[str, ...]] = {
    1: ("A1", "A3", "A4", "A6", "A18", "A19"),
    2: ("A3", "A4", "A18", "A19"),
    3: ("A7", "A8", "A9", "A10", "A12", "A18"),
    4: ("A15", "A16", "A18"),
}


# --------------------------------------------------------------------------
# Contexto da pagina
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Contexto:
    """O que toda pagina precisa saber antes de desenhar qualquer coisa."""

    filtros: Filtros
    data_ref: date
    tema: Tema

    @property
    def ano(self) -> int:
        """Ano usado nas comparacoes com meta: o ano da ultima competencia do periodo."""
        return self.filtros.fim.year

    @property
    def competencia(self) -> tuple[date, date]:
        return (self.filtros.inicio, self.filtros.fim)

    @property
    def tem_recorte(self) -> bool:
        """Ha filtro dimensional ativo? (decide meta, escopo de custo e badges)."""
        f = self.filtros
        return bool(
            f.tem_recorte_cliente
            or f.tipos_contrato
            or f.status_contrato
            or f.tipos_receita
            or f.categorias_veiculo
            or f.categorias_custo
            or f.tipos_custo
        )


def contexto() -> Contexto:
    """Le o estado global montado pela barra lateral do ``streamlit_app.py``.

    Sem ``session_state`` (a view rodando isolada num teste) cai para
    ``Filtros()`` padrao -- e a pagina renderiza igual.
    """
    filtros: Filtros = st.session_state.get("filtros") or Filtros()
    return Contexto(
        filtros=filtros,
        data_ref=filtros.ref,
        tema=ui.tema_atual(),
    )


def chips_contexto(
    ctx: Contexto, *, pagina: int, periodo_total: bool = False
) -> list[str]:
    """Os recortes que produziram os numeros desta tela, prontos para o cabecalho.

    Inclui os **recortes dimensionais** (segmento, porte, rating, tipo de contrato,
    cliente), que antes so existiam na barra lateral: com ela recolhida, os numeros
    mudavam sem nada na tela dizendo por que.
    """
    f = ctx.filtros
    exibidos = FILTROS_DA_PAGINA.get(pagina, ())
    if periodo_total:
        # No Guia o chip anuncia o que **existe** para analisar, nao o recorte em
        # vigor: quem abre a pagina de orientacao com o filtro em "ultimos 12m"
        # concluiria que 2024 nao esta no dashboard.
        ini, fim, quando = config.COMPETENCIA_MIN, config.COMPETENCIA_MAX, config.DATA_EXTRACAO
        chips = [f"Dados de {fmt.periodo(ini, fim)}"]
    else:
        ini, fim, quando = f.inicio, f.fim, ctx.data_ref
        chips = []
        if "ano" in exibidos:
            chips.append(f"Exercício {fim.year}")
        elif "periodo" in exibidos:
            chips.append(f"Período de {fmt.periodo(ini, fim)}")
        if "data" in exibidos:
            chips.append(f"Como estava em {fmt.data_br(quando)}")
        # So quando sai do padrao: um chip "Por mês" em toda tela seria ruido,
        # mas trimestre ou ano mudam a magnitude de cada barra e precisam aparecer.
        if "granularidade" in exibidos and grao_atual() != GRAO_PADRAO:
            chips.append(f"Agrupado por {NOME_DO_GRAO[grao_atual()]}")
    for chave, rotulo, valores in (
        ("segmento", "Segmento", f.segmentos),
        ("porte", "Porte", f.portes),
        ("rating", "Rating", f.ratings),
        ("tipo_contrato", "Tipo de contrato", f.tipos_contrato),
        ("cliente", "Cliente", f.clientes),
    ):
        if not valores or (exibidos and chave not in exibidos):
            continue
        # Ate dois valores cabem por extenso; acima disso o chip vira contagem,
        # senao um filtro de oito segmentos empurra o titulo para fora da tela.
        if len(valores) <= 2:
            chips.append(f"{rotulo}: {', '.join(rot.valor(v) for v in valores)}")
        else:
            chips.append(f"{rotulo}: {len(valores)} selecionados")
    return chips


def abrir_pagina(
    ctx: Contexto, titulo: str, *, secao: str, pagina: int,
    periodo_total: bool = False,
) -> None:
    """Estilos + cabecalho. Primeira chamada de toda pagina.

    O titulo **e** a pergunta da pagina; ``secao`` e o nome curto que aparece no
    menu, e que o cabecalho repete para o leitor saber onde esta.
    """
    ui.estilos(ctx.tema)
    ui.cabecalho_pagina(
        secao, titulo,
        chips=chips_contexto(ctx, pagina=pagina, periodo_total=periodo_total),
        tema=ctx.tema,
    )


# --------------------------------------------------------------------------
# Carregamento
# --------------------------------------------------------------------------


def _com_contexto(ctx_script: Any, fn: Callable[[], Any]) -> Any:
    if ctx_script is not None:
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx

            add_script_run_ctx(threading.current_thread(), ctx_script)
        except Exception:  # noqa: BLE001 - sem contexto o cache so fica mais barulhento
            pass
    return fn()


def carregar(tarefas: Mapping[str, Callable[[], Any]], *, trabalhadores: int = 5) -> dict[str, Any]:
    """Executa as consultas da pagina em paralelo e devolve ``{nome: resultado}``.

    Uma metrica que falha **nao derruba a pagina**: a excecao vira o valor da
    chave e a view mostra o erro so naquele bloco. Use :func:`obter` para ler.
    """
    if not tarefas:
        return {}
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx_script = get_script_run_ctx()
    except Exception:  # noqa: BLE001
        ctx_script = None
    resultados: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(trabalhadores, len(tarefas)))) as executor:
        futuros = {
            nome: executor.submit(_com_contexto, ctx_script, fn) for nome, fn in tarefas.items()
        }
        for nome, futuro in futuros.items():
            try:
                resultados[nome] = futuro.result()
            except Exception as exc:  # noqa: BLE001 - erro por metrica, nao por pagina
                resultados[nome] = exc
    return resultados


def obter(dados: Mapping[str, Any], chave: str) -> pd.DataFrame | None:
    """DataFrame da chave, ou ``None`` se a metrica falhou ou veio vazia."""
    valor = dados.get(chave)
    if isinstance(valor, Exception) or valor is None:
        return None
    if isinstance(valor, pd.DataFrame):
        return valor if not valor.empty else None
    return valor


def falhou(dados: Mapping[str, Any], chave: str) -> str | None:
    """Mensagem tecnica quando a metrica levantou excecao (para o expander)."""
    valor = dados.get(chave)
    if isinstance(valor, Exception):
        return f"{type(valor).__name__}: {valor}"
    return None


@st.cache_data(ttl=config.TTL_PESADO, show_spinner=False, max_entries=64)
def avaliar_alertas(filtros: Filtros, data_ref: date, ids: tuple[str, ...]) -> pd.DataFrame:
    """``alertas.avaliar`` cacheado por (recorte, foto, subconjunto de regras).

    O subconjunto vem de :data:`ALERTAS_DA_PAGINA`, nunca de um ``if`` na view.
    """
    return m_alertas.avaliar(filtros, data_ref, ids=list(ids))


def limiares_de(df_alertas: pd.DataFrame | None, id_alerta: str) -> tuple[float | None, float | None]:
    """Le ``(ambar, vermelho)`` de uma regra -- a UI nunca escreve um limiar.

    Devolve ``(None, None)`` quando a regra nao foi avaliada nesta pagina: sem
    limiar, ``format.delta`` mantem o desvio desfavoravel em **neutro**.
    """
    if df_alertas is None or df_alertas.empty or "id" not in df_alertas.columns:
        return (None, None)
    linha = df_alertas[df_alertas["id"] == id_alerta]
    if linha.empty:
        return (None, None)
    ambar = linha.iloc[0].get("limiar_ambar")
    vermelho = linha.iloc[0].get("limiar_vermelho")
    return (
        None if fmt.eh_vazio(ambar) else abs(float(ambar)),
        None if fmt.eh_vazio(vermelho) else abs(float(vermelho)),
    )


#: Traducao da direcao publicada pela camada de alertas para a direcao do tema.
_DIRECAO_ALERTA: Mapping[str, str] = {
    "maior_pior": "menor_melhor",
    "menor_pior": "maior_melhor",
    "evento": "neutro",
}


def nivel_do_valor(df_alertas: pd.DataFrame | None, id_alerta: str, valor: Any) -> str:
    """Nivel visual de um valor contra os limiares **publicados** de uma regra.

    A view passa o numero e o id da regra; quem decide o corte e
    ``alertas.avaliar()``. Sem a regra no frame, devolve ``"neutro"``.
    """
    if df_alertas is None or df_alertas.empty or "id" not in df_alertas.columns:
        return "neutro"
    linha = df_alertas[df_alertas["id"] == id_alerta]
    if linha.empty or fmt.eh_vazio(valor):
        return "neutro"
    registro = linha.iloc[0]
    direcao = _DIRECAO_ALERTA.get(str(registro.get("direcao")), "menor_melhor")
    if direcao == "neutro":
        return "neutro"
    ambar = registro.get("limiar_ambar")
    vermelho = registro.get("limiar_vermelho")
    nivel = theme.nivel_por_limiar(
        float(valor),
        ambar=None if fmt.eh_vazio(ambar) else float(ambar),
        vermelho=None if fmt.eh_vazio(vermelho) else float(vermelho),
        direcao=direcao,  # type: ignore[arg-type]
    )
    return "neutro" if nivel == "bom" else nivel


# --------------------------------------------------------------------------
# Leitura defensiva de celulas
# --------------------------------------------------------------------------


def celula(df: pd.DataFrame | None, coluna: str, linha: int = 0) -> float | None:
    """Valor numerico de uma celula, ou ``None`` quando a metrica veio sem valor.

    A camada semantica devolve **uma linha com celulas nulas** (nao um frame
    vazio) quando o recorte nao encontra titulo nenhum. ``obter()`` nao filtra
    esse caso porque o frame nao esta vazio; ler com ``float()`` direto derruba
    a pagina.
    """
    if df is None or df.empty or coluna not in df.columns or linha >= len(df):
        return None
    valor = df.iloc[linha][coluna]
    return None if fmt.eh_vazio(valor) else float(valor)


def texto_celula(df: pd.DataFrame | None, coluna: str, linha: int = 0) -> str | None:
    """Valor textual de uma celula, ou ``None``."""
    if df is None or df.empty or coluna not in df.columns or linha >= len(df):
        return None
    valor = df.iloc[linha][coluna]
    return None if fmt.eh_vazio(valor) else str(valor)


def soma(df: pd.DataFrame | None, coluna: str) -> float | None:
    """Soma de uma coluna, ``None`` quando ela nao existe ou e toda nula."""
    if df is None or df.empty or coluna not in df.columns:
        return None
    valores = pd.to_numeric(df[coluna], errors="coerce")
    return None if valores.notna().sum() == 0 else float(valores.sum())


def do_ano(df: pd.DataFrame | None, ano: int, coluna: str) -> float | None:
    """Valor de ``coluna`` na linha do ``ano`` (frames ``*_por_ano``)."""
    if df is None or "ano" not in df.columns or coluna not in df.columns:
        return None
    linha = df[df["ano"] == ano]
    if linha.empty:
        return None
    valor = linha.iloc[0][coluna]
    return None if fmt.eh_vazio(valor) else float(valor)


def valor_da_serie(indice: pd.DataFrame, mes: str, coluna: str) -> float | None:
    """Valor de ``coluna`` no ``mes`` de uma serie indexada por ``ano_mes``.

    Devolve ``None`` quando o mes nao existe **ou** quando a celula e nula: um
    recorte sem titulo nenhum devolve a serie inteira de meses com as celulas em
    ``pd.NA``, e as anotacoes fixas do grafico tem que sumir, nao explodir.
    """
    if mes not in indice.index or coluna not in indice.columns:
        return None
    valor = indice.loc[mes, coluna]
    return None if fmt.eh_vazio(valor) else float(valor)


def maximo_da_coluna(df: pd.DataFrame, coluna: str, padrao: float = 0.0) -> float:
    """Maximo numerico de uma coluna, com ``padrao`` quando tudo e nulo."""
    if coluna not in df.columns or df.empty:
        return padrao
    valor = df[coluna].max()
    return padrao if fmt.eh_vazio(valor) else float(valor)


def texto_periodo(periodo_realizado: Any) -> str:
    """``'2026-01..2026-08'`` -> ``'jan/2026 a ago/2026'``.

    O rodape do tile **tem** que dizer qual janela de meta foi usada: os erros de
    comparacao do projeto nasceram de comparar 8 meses de realizado com meta
    anual.
    """
    texto = str(periodo_realizado or "")
    if ".." not in texto:
        return texto
    ini, _, fim = texto.partition("..")
    return fmt.periodo(ini.strip(), fim.strip())


def linha_meta(df: pd.DataFrame | None, tipo_meta: str) -> pd.Series | None:
    """Linha de ``metas.comparativo_anual`` de um indicador, ou ``None``."""
    if df is None or "tipo_meta" not in df.columns:
        return None
    linha = df[df["tipo_meta"] == tipo_meta]
    return None if linha.empty else linha.iloc[0]


# --------------------------------------------------------------------------
# Faixa de KPIs -- cada pagina monta a sua, com os KPIs da sua pergunta
# --------------------------------------------------------------------------


def faixa_kpis(itens: Sequence[Mapping[str, Any]], *, tema: Tema) -> None:
    """Renderiza uma linha de tiles de KPI.

    Cada item e o ``kwargs`` de :func:`frotas.ui.componentes.tile_kpi`. A faixa
    nao e mais identica nas paginas: cada pagina mostra os KPIs da **sua**
    pergunta, o que tambem evita pagar a consulta de meta em pagina que nao
    fala de meta.
    """
    if not itens:
        return
    colunas = st.columns(len(itens), gap="medium")
    for coluna, item in zip(colunas, itens):
        with coluna:
            ui.tile_kpi(tema=tema, **item)


def alertas_da_pagina(
    df_alertas: pd.DataFrame | None,
    pagina: int,
    *,
    destinos: Mapping[str, str] | None = None,
) -> list[ui.Alerta]:
    """Alertas disparados **mais** os que nao se aplicam ao recorte, em cinza.

    Sem a segunda parte, uma pagina com filtro dimensional mostraria "nenhum
    limiar atingido" em verde justamente quando as regras de meta deixaram de
    valer -- e ``indisponivel`` nunca pode virar boa noticia.
    ``ui.alertas_da_camada`` traduz ``indisponivel`` para o nivel neutro, que o
    banner desenha em cinza e ordena por ultimo.
    """
    if df_alertas is None or df_alertas.empty:
        return []
    # O recorte vem de :data:`ALERTAS_DA_PAGINA` -- o que **esta pagina** pediu para
    # avaliar -- e nao do campo ``pagina`` do limiar. Uma regra pode interessar a mais
    # de uma tela: eficiencia de cobranca (A4) e faturamento contra a meta (A3) valem
    # tanto na pagina de metas quanto na de faturamento e recebimento. Enquanto o
    # filtro olhava o campo, a pagina 2 pedia A3 e A4 e nao mostrava nenhum dos dois.
    ids = ALERTAS_DA_PAGINA.get(pagina, ())
    do_escopo = df_alertas[df_alertas["id"].isin(ids)] if ids else df_alertas.iloc[0:0]
    # As regras de qualidade de dado (A18, A19) ficam fora do banner: quem as mostra
    # e :func:`barra_qualidade`, em tom informativo, no fim da pagina. Sem esta
    # linha elas apareceriam duas vezes na mesma tela.
    if "pagina" in do_escopo.columns:
        do_escopo = do_escopo[do_escopo["pagina"] != 0]
    disparados = ui.alertas_da_camada(do_escopo, destinos=destinos)
    nao_aplicaveis = ui.alertas_da_camada(
        do_escopo[do_escopo["nivel"] == "indisponivel"],
        destinos=destinos, incluir_ok=True,
    )
    return disparados + nao_aplicaveis


def regras_da_pagina(df_alertas, pagina: int) -> int:
    """Quantas regras de alerta existem para esta pagina (tenham disparado ou nao).

    O banner usa isto para diferenciar "avaliei e esta tudo bem" de "nao existe
    regra aqui". Sem a distincao, uma pagina sem regra exibe verde para sempre.
    """
    if df_alertas is None or df_alertas.empty:
        return 0
    return int(df_alertas["id"].isin(ALERTAS_DA_PAGINA.get(pagina, ())).sum())


def barra_qualidade(df_alertas: pd.DataFrame | None, *, tema: Tema = "claro") -> None:
    """Barra discreta de qualidade de dado (A18, A19), em **todas** as paginas.

    Tom ``info``, **nunca** vermelho: sao avisos de definicao e de processo; se
    fossem pintados como alerta, competiriam com o risco real.
    """
    if df_alertas is None or df_alertas.empty or "pagina" not in df_alertas.columns:
        return
    linhas = df_alertas[
        (df_alertas["pagina"] == 0) & (df_alertas["nivel"].isin(("vermelho", "ambar")))
    ]
    for _, linha in linhas.iterrows():
        # Sem o id da regra ("A18 ·"): e rastreabilidade com docs/01_kpis.md, nao
        # informacao para quem le o painel.
        ui.nota_armadilha(str(linha["detalhe"]))


# --------------------------------------------------------------------------
# Graficos
# --------------------------------------------------------------------------


def nova_figura(tema: Tema, *, altura: int = 320, **layout: Any) -> go.Figure:
    """Figura Plotly ja com o chrome do tema (grade em fio de cabelo, sem sombra)."""
    fig = go.Figure()
    base = theme.layout_grafico(tema)
    base["height"] = altura
    base["hovermode"] = "x unified"
    base["showlegend"] = False
    base.update(layout)
    fig.update_layout(**base)
    return fig


def datas_de(meses: Sequence[str]) -> list[pd.Timestamp]:
    """``'2026-08'`` -> ``Timestamp('2026-08-01')``.

    O eixo x mensal e temporal, nao categorico: e isso que permite anotacao com
    linha vertical e faixa (``add_vline`` / ``add_vrect``) sem gambiarra.
    """
    return [pd.Timestamp(str(m)[:7] + "-01") for m in meses]


def rotulos_mensais(meses: Sequence[str]) -> list[str]:
    """Rotulos de um eixo mensal: so janeiro leva o ano (``jan/25``); o resto, o mes."""
    textos = []
    for mes in meses:
        rotulo = fmt.competencia(mes)
        textos.append(rotulo if str(mes)[5:7] == "01" else rotulo.split("/")[0])
    return textos


#: Granularidade do eixo x nos graficos temporais. Rotulo -> chave interna.
#:
#: **Semana nao entra, e nao e esquecimento**: no banco, ``titulos_receber.competencia``
#: e ``custos.competencia`` sao sempre dia 1 do mes -- o faturamento e o custo
#: nascem mensais e nao existe semana para desagregar. So ``data_pagamento`` tem
#: grao diario. Uma opcao "semana" entregaria o mes inteiro empilhado na primeira
#: semana em quase todo grafico do app.
GRAOS: Mapping[str, str] = {"Mês": "mes", "Trimestre": "trimestre", "Ano": "ano"}

#: Grao usado quando a pagina nao oferece o seletor.
GRAO_PADRAO = "mes"

#: Sufixo do titulo do eixo Y: "R$ no mes" vira "R$ no trimestre". Um eixo que
#: diz "no mes" com barras trimestrais mente sobre a magnitude.
#: Nome do grao para o chip de contexto e para o titulo do eixo.
NOME_DO_GRAO: Mapping[str, str] = {"mes": "mês", "trimestre": "trimestre", "ano": "ano"}

NO_PERIODO: Mapping[str, str] = {
    "mes": "no mês", "trimestre": "no trimestre", "ano": "no ano",
}



def grao_atual() -> str:
    """Granularidade escolhida na barra lateral, ou ``mes``."""
    return GRAOS.get(str(st.session_state.get("granularidade", "")), GRAO_PADRAO)


def _inicio_do_balde(ano_mes: Any, grao: str) -> str:
    """Primeiro mes do balde a que ``ano_mes`` pertence, em ``'YYYY-MM'``."""
    texto = str(ano_mes)[:7]
    ano, mes = int(texto[:4]), int(texto[5:7])
    if grao == "trimestre":
        mes = (mes - 1) // 3 * 3 + 1
    elif grao == "ano":
        mes = 1
    return f"{ano:04d}-{mes:02d}"


def reagrupar(
    df: pd.DataFrame,
    *,
    grao: str,
    soma: Sequence[str] = (),
    fim: Sequence[str] = (),
    razao: Mapping[str, tuple[str, str]] | None = None,
    coluna: str = "ano_mes",
) -> pd.DataFrame:
    """Reagrupa uma serie mensal em trimestre ou ano, coluna a coluna.

    Cada coluna precisa dizer **como** se agrega, porque nao existe regra unica:

    - ``soma``: valores em reais e contagens, que se acumulam no periodo;
    - ``fim``: indicador de fim de periodo (a inadimplencia e uma foto na data,
      entao o trimestre e o valor do ultimo mes dele, nunca a soma dos tres);
    - ``razao``: ``{coluna: (numerador, denominador)}`` -- a taxa e **recalculada**
      sobre os totais do balde. A ociosidade trimestral e veiculos-mes parados
      sobre veiculos-mes de frota, e nao a media das tres taxas mensais, que
      pesaria igual um mes de frota pequena e um de frota grande.

    Devolve ``coluna`` reescrita com o primeiro mes do balde (o eixo continua
    temporal) e uma coluna ``rotulo_periodo`` com o texto do tick.
    """
    if df is None or df.empty:
        return df
    saida = df.copy().sort_values(coluna)
    if grao != "mes":
        saida[coluna] = [_inicio_do_balde(v, grao) for v in saida[coluna]]
        agregacoes: dict[str, Any] = {c: "sum" for c in soma if c in saida.columns}
        # ``min_count=1``: um balde sem nenhum realizado fica nulo, nao zero. O
        # futuro de 2026 nao pode virar uma barra no chao.
        for c in list(agregacoes):
            agregacoes[c] = lambda x: x.sum(min_count=1)
        for c in fim:
            if c in saida.columns:
                agregacoes[c] = lambda x: x.dropna().iloc[-1] if x.notna().any() else float("nan")
        for _, (num, den) in (razao or {}).items():
            for c in (num, den):
                if c in saida.columns:
                    agregacoes.setdefault(c, lambda x: x.sum(min_count=1))
        # Colunas sem regra (unidade, tipo_agregacao) sao constantes na serie:
        # o balde herda a primeira.
        for c in saida.columns:
            if c != coluna and c not in agregacoes:
                agregacoes[c] = "first"
        saida = saida.groupby(coluna, as_index=False, sort=True).agg(agregacoes)
        for destino, (num, den) in (razao or {}).items():
            if num in saida.columns and den in saida.columns:
                saida[destino] = 100.0 * saida[num] / saida[den].replace(0, pd.NA)
    formatar = {"mes": fmt.competencia, "trimestre": fmt.trimestre, "ano": fmt.ano_civil}[grao]
    saida["rotulo_periodo"] = [formatar(v) for v in saida[coluna]]
    return saida.reset_index(drop=True)


def eixo_temporal(
    fig: go.Figure, df: pd.DataFrame, *, grao: str,
    titulo: str = "Mês de competência", coluna: str = "ano_mes",
) -> None:
    """Ticks e titulo do eixo x no grao escolhido.

    O titulo muda junto: "Mês de competência" vira "Trimestre de competência". Um
    eixo que diz "Mês" com barras trimestrais e pior que eixo sem titulo.
    """
    nome = NOME_DO_GRAO[grao].capitalize()
    titulo_grao = titulo.replace("Mês", nome, 1) if titulo.startswith("Mês") else titulo
    fig.update_xaxes(
        tickmode="array",
        tickvals=datas_de(df[coluna]),
        ticktext=(list(df["rotulo_periodo"]) if "rotulo_periodo" in df.columns
                  else rotulos_mensais(df[coluna])),
        title_text=titulo_grao,
        title_font_size=theme.TIPOGRAFIA["nota"],
    )


def eixo_mensal(fig: go.Figure, meses: Sequence[str], titulo: str = "Mês de competência") -> None:
    """Aplica os ticks mensais e o rotulo obrigatorio de eixo.

    O eixo x temporal sempre diz **qual** tempo -- competencia, caixa ou data de
    referencia. Nunca "data".
    """
    fig.update_xaxes(
        tickmode="array",
        tickvals=datas_de(meses),
        ticktext=rotulos_mensais(meses),
        title_text=titulo,
        title_font_size=theme.TIPOGRAFIA["nota"],
    )


def mostrar_grafico(
    fig: go.Figure,
    *,
    chave: str,
    nota: str | None = None,
    dados: pd.DataFrame | None = None,
    colunas_dados: Sequence[str] | None = None,
    rotulos_dados: Mapping[str, str] | None = None,
    rotulo_expander: str = "ver dados do gráfico",
    tabela: bool = False,
) -> None:
    """Renderiza o grafico com a alternativa textual obrigatoria.

    ``nota`` e **nota de rodape do visual**, nao paragrafo de pagina: entra so
    quando o numero nao se interpreta sozinho (uma definicao, uma ressalva de
    comparabilidade). Descrever em prosa o que o grafico ja mostra e exatamente
    o que saiu nesta rodada.

    ``tabela`` liga o expander com os numeros do grafico. Ele e **opt-in**: um
    "ver dados do grafico" embaixo de cada um dos catorze visuais do app poluia
    mais do que ajudava. Os parametros ``dados``/``colunas_dados``/
    ``rotulos_dados`` continuam aceitos para quem quiser ligar ponto a ponto.
    """
    st.plotly_chart(fig, use_container_width=True, key=chave, config={"displaylogo": False})
    if nota:
        # Duas cifras na mesma nota abririam LaTeX no Markdown do Streamlit.
        st.caption(fmt.sem_latex(nota))
    if tabela and dados is not None and not dados.empty:
        with st.expander(rotulo_expander):
            st.dataframe(
                rot.renomear(dados, extras=rotulos_dados, apenas=colunas_dados),
                hide_index=True,
                width="stretch",
            )


# --------------------------------------------------------------------------
# Leitura executiva
# --------------------------------------------------------------------------


@st.cache_data(ttl=config.TTL_PESADO, show_spinner=False, max_entries=32)
def _gerar_leitura(payload_json: str) -> dict:
    """Chama o modelo uma vez por payload. A chave de cache e o proprio JSON.

    Sem isto, cada rerun do Streamlit -- e ha um a cada clique de filtro --
    dispararia uma chamada nova e cobraria de novo pela mesma leitura.
    """
    import json as _json

    resultado = ia.gerar(_json.loads(payload_json))
    return {
        "texto": resultado.texto,
        "conferidos": resultado.conferencia.conferidos,
        "tokens_entrada": resultado.tokens_entrada,
        "tokens_saida": resultado.tokens_saida,
        "tentativas": resultado.tentativas,
        "custo": resultado.custo_estimado_reais,
    }


def leitura_executiva(ctx: Contexto, *, comp: pd.DataFrame | None,
                      df_alertas: pd.DataFrame | None) -> None:
    """Bloco da leitura executiva: botao, texto aprovado e o selo de conferencia.

    O modelo nao consulta nada. Recebe o payload que :mod:`frotas.leitura` monta a
    partir do que a camada de metricas ja apurou, e a resposta so chega a tela
    depois de passar na conferencia de procedencia.
    """
    import json as _json

    if not ia.disponivel():
        # A presenca da credencial **e** o interruptor, e por isso nao existe
        # deteccao de ambiente aqui: na maquina do autor a chave esta no .env e o
        # botao funciona; na versao publicada o segredo simplesmente nao e
        # configurado e o visitante ve o recado abaixo. Um unico caminho de codigo
        # para os dois casos, sem flag para esquecer de virar.
        ui.frase(
            "Aqui o Claude leria os números desta página e escreveria o resumo do "
            "exercício: o que vai bem, o que preocupa e o que fazer primeiro."
        )
        st.button("Gerar a leitura do exercício", icon=":material/auto_awesome:",
                  disabled=True, key="leitura_desligada")
        # Tom "info", nao "aviso": nada aqui esta errado, e o glifo de alerta
        # brigaria com a piada.
        ui.nota_armadilha(
            "Acontece que cada clique nesse botão sai do meu bolso, e o bolso é modesto. "
            "Então na versão publicada ele fica desligado mesmo, haha. Obrigado por "
            "testar! Se quiser ver funcionando, roda o projeto na sua máquina com uma "
            "chave da API do Claude: aí o crédito é seu.",
        )
        return

    with st.spinner("Lendo os números..."):
        payload = _montar_payload_leitura(ctx, comp=comp, df_alertas=df_alertas)
    assinatura = _json.dumps(payload, ensure_ascii=False, sort_keys=True)

    chave_estado = f"leitura_{ctx.ano}"
    if st.button("Gerar a leitura do exercício", icon=":material/auto_awesome:"):
        st.session_state[chave_estado] = assinatura

    if st.session_state.get(chave_estado) != assinatura:
        ui.frase(
            "Um resumo do exercício em três parágrafos: o que vai bem, o que preocupa e "
            "a ação mais urgente. Escrito a partir dos números desta página, e conferido "
            "número a número antes de aparecer."
        )
        return

    try:
        with st.spinner("Escrevendo a leitura..."):
            saida = _gerar_leitura(assinatura)
    except ia.LeituraIndisponivel as exc:
        st.warning(exc.mensagem_usuario)
        return

    ui.leitura_gerada(
        saida["texto"],
        rodape=(f"{saida['conferidos']} números conferidos contra a camada de métricas, "
                f"nenhum inventado · {fmt.moeda(saida['custo'])} nesta leitura"),
        tema=ctx.tema,
    )


def _montar_payload_leitura(ctx: Contexto, *, comp: pd.DataFrame | None,
                            df_alertas: pd.DataFrame | None) -> dict:
    """Junta o que as metricas ja calcularam no dicionario que vai para o modelo."""
    from frotas.metrics import credito, custos, receita

    f, ref = ctx.filtros, ctx.data_ref
    f_ano = f.com(competencia_ini=date(ctx.ano, 1, 1),
                  competencia_fim=config.COMPETENCIA_MAX)

    def primeira(df: pd.DataFrame | None) -> dict | None:
        if df is None or df.empty:
            return None
        return df.iloc[0].to_dict()

    def linhas(df: pd.DataFrame | None, limite: int | None = None) -> list[dict]:
        if df is None or df.empty:
            return []
        recorte = df if limite is None else df.head(limite)
        return [linha.to_dict() for _, linha in recorte.iterrows()]

    tarefas = {
        "resumo": lambda: receita.resumo(f_ano),
        "cobertura": lambda: credito.cobertura_de_caixa(f, ref),
        "inad": lambda: credito.inadimplencia_ponto_no_tempo(f, ref),
        "segmentos": lambda: credito.risco_por_segmento(f, ref),
        "aging": lambda: credito.aging_carteira(f, ref),
        "ociosidade": lambda: custos.custo_ociosidade(f_ano),
    }
    dados = carregar(tarefas, trabalhadores=6)

    seg = obter(dados, "segmentos")
    if seg is not None and not seg.empty:
        seg = seg.sort_values("inadimplencia_pct", ascending=False)
    ocio = obter(dados, "ociosidade")

    return ia.montar_payload(
        exercicio=ctx.ano,
        data_ref=ref,
        resumo=primeira(obter(dados, "resumo")),
        cobertura=primeira(obter(dados, "cobertura")),
        inadimplencia=primeira(obter(dados, "inad")),
        # Rotulos traduzidos antes de sair: o modelo escreve o que le, e um payload
        # com "Servicos Publicos" devolveria "Servicos Publicos" na tela.
        metas_do_ano=[{**linha, "tipo_meta": rot.valor(linha.get("tipo_meta"))}
                      for linha in linhas(comp)],
        # So os alertas que estao doendo: uma lista com treze regras, das quais duas
        # em "ok", faria o modelo gastar paragrafo com o que esta em ordem.
        alertas=[a for a in linhas(df_alertas)
                 if str(a.get("nivel")) in ("ambar", "vermelho")],
        segmentos=[{**linha, "segmento": rot.valor(linha.get("segmento"))}
                   for linha in linhas(seg, 4)],
        aging=[{**linha, "faixa": rot.faixa_aging(linha.get("faixa"))}
               for linha in linhas(obter(dados, "aging"))],
        ociosidade=(None if ocio is None or ocio.empty else ocio.iloc[-1].to_dict()),
    )


def cor_divergente(delta: float | None, *, direcao: str, limite: float, tema: Tema) -> str:
    """Cor de um desvio na escala divergente, por **favorabilidade** e nao por sinal."""
    escala = theme.escala_divergente(tema)
    posicao = theme.posicao_divergente(delta, direcao=direcao, limite=limite)  # type: ignore[arg-type]
    indice = int(round((posicao + 1) / 2 * (len(escala) - 1)))
    return escala[max(0, min(len(escala) - 1, indice))]


#: Acima disto o rotulo em cada marca vira ruido e some (32 meses de "Tudo" nao
#: cabem lado a lado). O hover e o eixo continuam respondendo.
MAX_MARCAS_ROTULADAS: int = 14


def rotulos_de_barra(valores: Sequence[Any], *, compacto: bool = True) -> dict[str, Any]:
    """``kwargs`` de rotulo direto para ``go.Bar``, ou vazio se houver marcas demais.

    Rotulo direto dispensa ler o eixo Y para saber o valor de cada mes -- que e o
    ponto de um dashboard. Acima de :data:`MAX_MARCAS_ROTULADAS` marcas ele sai.

    Sem o "R$" em cada marca: a unidade ja esta no titulo do eixo, e repeti-la
    doze vezes rouba largura da barra sem informar nada.
    """
    if len(valores) > MAX_MARCAS_ROTULADAS:
        return {}
    formatar = (
        (lambda v: fmt.moeda_compacta(v, prefixo=False)) if compacto
        else (lambda v: fmt.numero(v, 0))
    )
    return {
        "text": [formatar(v) for v in valores],
        "textposition": "outside",
        "textfont": {"size": theme.TIPOGRAFIA["nota"]},
        "cliponaxis": False,
    }


def rotular_ultimo_ponto(
    fig: go.Figure, x: Sequence[Any], y: Sequence[Any],
    texto: str | Callable[[Any], str], cor: str, *, tema: Tema,
) -> None:
    """Escreve o valor **do ultimo ponto** de uma serie, ao lado do marcador.

    Serie de linha nao ganha rotulo em todos os pontos: doze numeros sobre a
    linha competem com ela. O ultimo ponto e o que responde "quanto esta agora"
    sem obrigar a ler o eixo.
    """
    # O ultimo ponto **com valor**, nao o ultimo da serie: o mes corrente costuma
    # vir vazio, e ancorar nele fazia a anotacao sumir sem aviso (era o caso da
    # serie de inadimplencia, que ficava sem rotulo nenhum).
    pares = [(px, py) for px, py in zip(list(x), list(y)) if not fmt.eh_vazio(py)]
    if not pares:
        return
    ancora_x, ancora_y = pares[-1]
    # ``texto`` pode ser um formatador: assim o rotulo sai do **mesmo** ponto em
    # que a anotacao e ancorada. Passar a string pronta obrigava o chamador a
    # adivinhar qual era o ultimo ponto com valor, e quem usava ``iloc[-1]``
    # acabava formatando um vazio e perdendo a anotacao inteira.
    if callable(texto):
        texto = texto(ancora_y)
    if texto in ("", fmt.VAZIO):
        return
    fig.add_annotation(
        x=ancora_x, y=ancora_y, text=texto, showarrow=False,
        xanchor="left", yanchor="middle", xshift=8,
        font={"size": theme.TIPOGRAFIA["nota"], "color": cor},
        bgcolor=theme.tokens(tema).superficie, borderpad=2,
    )


def barra_horizontal(
    fig: go.Figure,
    categorias: Sequence[str],
    valores: Sequence[float],
    *,
    cores: Sequence[str],
    textos: Sequence[str],
    tema: Tema,
    hover: Sequence[str] | None = None,
) -> None:
    """Barra horizontal ordenada com rotulo direto -- a forma padrao do app.

    Rotulo direto sempre: e a regra de alivio da paleta (aqua, magenta e amarelo
    ficam abaixo de 3:1 no tema claro e nao podem aparecer sem rotulo).
    """
    t = theme.tokens(tema)
    fig.add_trace(
        go.Bar(
            x=list(valores), y=list(categorias), orientation="h",
            marker={"color": list(cores),
                    "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
            text=list(textos), textposition="outside",
            textfont={"size": theme.TIPOGRAFIA["nota"], "color": t.tinta_secundaria},
            hovertext=list(hover) if hover else None,
            hoverinfo="text" if hover else None,
        )
    )
    fig.update_layout(hovermode="closest", bargap=0.35)
    fig.update_yaxes(autorange="reversed", showgrid=False)


def barra_empilhada_100(
    fig: go.Figure,
    partes: Sequence[tuple[str, float, float, str]],
    *,
    tema: Tema,
    minimo_rotulo: float = 8.0,
) -> None:
    """Barra unica de composicao (100%), com rotulo dentro das fatias grandes.

    ``partes`` = ``(nome, participacao_pct, valor_absoluto, cor)``.
    """
    t = theme.tokens(tema)
    for nome, participacao, valor, cor in partes:
        fig.add_trace(
            go.Bar(
                x=[participacao], y=[""], orientation="h", name=nome,
                marker={"color": cor,
                        "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
                text=f"{nome}<br>{fmt.percentual(participacao, 1)}"
                if participacao >= minimo_rotulo else "",
                textposition="inside", insidetextanchor="middle",
                textfont={"size": theme.TIPOGRAFIA["nota"], "color": t.superficie},
                hovertemplate=(f"{nome}<br>{fmt.moeda(valor)}<br>"
                               f"{fmt.percentual(participacao, 1)}<extra></extra>"),
            )
        )
    fig.update_layout(barmode="stack", showlegend=False)
    fig.update_yaxes(showticklabels=False, showgrid=False)




__all__ = [
    "ROTAS", "ALERTAS_DA_PAGINA", "Contexto", "contexto", "abrir_pagina",
    "carregar", "obter", "falhou", "avaliar_alertas", "limiares_de", "nivel_do_valor",
    "celula", "texto_celula", "soma", "do_ano", "valor_da_serie", "maximo_da_coluna",
    "texto_periodo", "linha_meta", "faixa_kpis", "alertas_da_pagina", "barra_qualidade",
    "nova_figura", "eixo_mensal", "rotulos_mensais", "datas_de", "mostrar_grafico",
    "cor_divergente", "barra_horizontal", "barra_empilhada_100", "chips_contexto",
    "regras_da_pagina",
]
