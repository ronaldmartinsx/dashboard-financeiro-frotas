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

from frotas import config
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
    1: ("periodo", "segmento"),
    2: ("periodo", "data", "segmento", "porte", "rating", "tipo_contrato", "cliente"),
    3: ("data", "segmento", "porte", "rating", "tipo_contrato", "cliente"),
    4: ("periodo", "data", "segmento", "porte", "rating", "tipo_contrato", "cliente"),
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
        chips = [f"Período de {fmt.periodo(ini, fim)}"] if "periodo" in exibidos else []
        if "data" in exibidos:
            chips.append(f"Como estava em {fmt.data_br(quando)}")
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
    disparados = ui.alertas_da_camada(df_alertas, paginas=[pagina], destinos=destinos)
    nao_aplicaveis = ui.alertas_da_camada(
        df_alertas[df_alertas["nivel"] == "indisponivel"],
        paginas=[pagina], destinos=destinos, incluir_ok=True,
    )
    return disparados + nao_aplicaveis


def regras_da_pagina(df_alertas, pagina: int) -> int:
    """Quantas regras de alerta existem para esta pagina (tenham disparado ou nao).

    O banner usa isto para diferenciar "avaliei e esta tudo bem" de "nao existe
    regra aqui". Sem a distincao, uma pagina sem regra exibe verde para sempre.
    """
    if df_alertas is None or df_alertas.empty:
        return 0
    return int((df_alertas["pagina"] == pagina).sum())


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
        ui.nota_armadilha(f"{linha['id']} · {linha['detalhe']}")


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
) -> None:
    """Renderiza o grafico com a alternativa textual obrigatoria.

    ``nota`` e **nota de rodape do visual**, nao paragrafo de pagina: entra so
    quando o numero nao se interpreta sozinho (uma definicao, uma ressalva de
    comparabilidade). Descrever em prosa o que o grafico ja mostra e exatamente
    o que saiu nesta rodada.

    O expander "ver dados" passa o frame por :func:`frotas.ui.rotulos.renomear`:
    era a maior fonte de nome de coluna cru no app.
    """
    st.plotly_chart(fig, use_container_width=True, key=chave, config={"displaylogo": False})
    if nota:
        st.caption(nota)
    if dados is not None and not dados.empty:
        with st.expander(rotulo_expander):
            st.dataframe(
                rot.renomear(dados, extras=rotulos_dados, apenas=colunas_dados),
                hide_index=True,
                width="stretch",
            )


def cor_divergente(delta: float | None, *, direcao: str, limite: float, tema: Tema) -> str:
    """Cor de um desvio na escala divergente, por **favorabilidade** e nao por sinal."""
    escala = theme.escala_divergente(tema)
    posicao = theme.posicao_divergente(delta, direcao=direcao, limite=limite)  # type: ignore[arg-type]
    indice = int(round((posicao + 1) / 2 * (len(escala) - 1)))
    return escala[max(0, min(len(escala) - 1, indice))]


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
