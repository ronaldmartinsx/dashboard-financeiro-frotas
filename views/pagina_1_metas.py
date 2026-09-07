"""Pagina 1 -- Metas. "Estamos entregando a meta?"

Quatro blocos, nesta ordem: os cinco indicadores orcados como KPI, o desvio do
ano contra a meta dos mesmos meses, a conferencia ano a ano e o acompanhamento
mensal do indicador escolhido. A quebra por segmento e opcional porque custa
~13 s.

Margem Operacional **nao existe** aqui: o seletor le ``metas.TIPOS_META`` (5
entradas), nunca o dominio da coluna, que ainda devolve 6.

Deliberadamente fora: serie historica de inadimplencia (o eixo 3 e a foto), as
duas versoes de orcamento lado a lado (vive na barra lateral) e qualquer
comparacao de meta por cliente, rating ou categoria -- essas metas nao existem.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frotas import config
from frotas.metrics import metas
from frotas.ui import componentes as ui
from frotas.ui import format as fmt
from frotas.ui import rotulos as rot
from frotas.ui import theme
from views import _comum as base

PAGINA = 1

#: Indicador orcado -> chave de direcao do tema (o que e "bom" para cada um).
DIRECAO: dict[str, str] = {
    "Faturamento": "faturamento_bruto",
    "Receita Liquida": "receita_liquida",
    "Recebimento (Caixa)": "recebimento_caixa",
    "Custo Operacional": "custo_operacional",
    "Inadimplencia > 30d": "inadimplencia_30d",
}

ctx = base.contexto()
base.abrir_pagina(ctx, "Estamos entregando a meta?", secao="Metas", pagina=PAGINA)

t = theme.tokens(ctx.tema)
f, ref, ano = ctx.filtros, ctx.data_ref, ctx.ano
grao = base.grao_atual()
ANOS = list(range(config.COMPETENCIA_MIN.year, config.COMPETENCIA_MAX.year + 1))

# O widget de segmento e lido do estado **antes** do carregamento: e ele que decide
# se a consulta mais cara entra no lote. O widget em si aparece la embaixo, na
# secao a que pertence.
st.session_state.setdefault("meta_segmento_indicador", metas.TIPOS_META[0])
indicador = st.session_state["meta_segmento_indicador"]
if indicador not in metas.TIPOS_META:
    indicador = st.session_state["meta_segmento_indicador"] = metas.TIPOS_META[0]
tem_segmento = indicador not in metas.SO_EMPRESA

tarefas: dict = {}
if tem_segmento:
    # Primeiro no lote de proposito: e a consulta mais cara da pagina (~13 s) e
    # precisa comecar junto com as outras, nao depois delas.
    tarefas["segmento"] = lambda: metas.comparativo_por_segmento(indicador, ano)
# As cinco series mensais vao juntas: ~0,6 s cada, em paralelo no mesmo lote.
for tipo in metas.TIPOS_META:
    tarefas[f"serie_{tipo}"] = lambda alvo=tipo: metas.serie_mensal(alvo, ano)
tarefas["alertas"] = lambda: base.avaliar_alertas(f, ref, base.ALERTAS_DA_PAGINA[PAGINA])
for a in ANOS:
    tarefas[f"comp_{a}"] = lambda alvo=a: metas.comparativo_anual(alvo)

with st.spinner("Apurando realizado e meta..."):
    dados = base.carregar(tarefas, trabalhadores=6)

df_alertas = base.obter(dados, "alertas")
comp = base.obter(dados, f"comp_{ano}")


# --------------------------------------------------------------------------
# Os cinco indicadores orcados
# --------------------------------------------------------------------------
ambar_inad, vermelho_inad = base.limiares_de(df_alertas, "A1")
parcial = bool(comp is not None and comp.iloc[0].get("eh_parcial"))
# Sem badge de ano parcial nos tiles: a nota logo abaixo da faixa ja explica o
# ano parcial uma vez. Repeti-la nos cinco cards era a mesma frase cinco vezes.

itens = []
for tipo in metas.TIPOS_META:
    reg = base.linha_meta(comp, tipo)
    percentual = reg is not None and str(reg.get("unidade")) == "%"
    meta_alinhada = None if reg is None else reg.get("meta_alinhada")
    if reg is None:
        rodape_meta = None
        contexto_anual = None
    elif percentual:
        rodape_meta = f"meta: {fmt.percentual(meta_alinhada, 2)}"
        contexto_anual = f"ano cheio: {fmt.pontos_percentuais(reg.get('variacao_abs_anual'))}"
    else:
        rodape_meta = f"meta: {fmt.moeda_compacta(meta_alinhada)}"
        contexto_anual = f"ano cheio: {fmt.moeda_compacta(reg.get('meta_anual'))}"
    itens.append(
        {
            "rotulo": rot.valor(tipo),
            "valor": None if reg is None else float(reg["realizado"]),
            "unidade": "pct" if percentual else "brl",
            "casas": 2 if percentual else None,
            "chave_direcao": DIRECAO[tipo],
            "meta": meta_alinhada,
            "delta": None if reg is None else reg.get(
                "variacao_abs_alinhada" if percentual else "variacao_pct_alinhada"
            ),
            "unidade_delta": "pp" if percentual else "pct",
            "ambar": ambar_inad if percentual else None,
            "vermelho": vermelho_inad if percentual else None,
            "periodo_meta": rodape_meta,
            "nota": contexto_anual,
            "estado": "erro" if reg is None else "normal",
            "ajuda": (
                "Leitura primaria: realizado contra a soma das metas dos mesmos meses. "
                "A leitura contra o ano cheio vai no rodape, como contexto."
            ),
        }
    )
base.faixa_kpis(itens, tema=ctx.tema)

ui.banner_alerta(
    base.alertas_da_pagina(
        df_alertas, PAGINA,
        destinos={"A1": base.ROTAS[3], "A3": base.ROTAS[2],
                  "A4": base.ROTAS[2], "A6": base.ROTAS[4]},
    ),
    maximo=3, tema=ctx.tema,
    regras_avaliadas=base.regras_da_pagina(df_alertas, PAGINA),
    estado="erro" if df_alertas is None else "normal", data_ref=ref,
)

if parcial:
    ui.nota_armadilha(
        f"{ano} tem {int(comp.iloc[0]['meses_realizados'])} meses de realizado. Toda comparação "
        "desta página usa a soma das metas dos mesmos meses; contra o orçamento do ano cheio o "
        "desvio de faturamento sairia em −31%, que não é performance, é calendário."
    )

# --------------------------------------------------------------------------
# Leitura executiva
# --------------------------------------------------------------------------
# Sob demanda, nunca no carregamento: a chamada custa dinheiro e o resto da pagina
# tem que abrir sem depender de rede. O botao e a unica coisa que aparece de graca.
ui.cabecalho_secao("O que estes números estão dizendo?", ancora="leitura")
base.leitura_executiva(ctx, comp=comp, df_alertas=df_alertas)

# --------------------------------------------------------------------------
# Onde ficamos em relacao a meta?
# --------------------------------------------------------------------------
ui.cabecalho_secao("Onde ficamos em relação à meta?", ancora="desvio")
if comp is None:
    ui.erro_metrica("o comparativo com a meta", base.falhou(dados, f"comp_{ano}"))
else:
    linhas = []
    for tipo in metas.TIPOS_META:
        reg = base.linha_meta(comp, tipo)
        if reg is None:
            continue
        percentual = str(reg.get("unidade")) == "%"
        desvio = reg.get("variacao_abs_alinhada" if percentual else "variacao_pct_alinhada")
        if fmt.eh_vazio(desvio):
            continue
        linhas.append(
            {
                "tipo": tipo,
                "percentual": percentual,
                "desvio": float(desvio),
                "realizado": reg.get("realizado"),
                "meta": reg.get("meta_alinhada"),
            }
        )
    if not linhas:
        ui.estado_vazio("Sem meta apurada para este ano")
    else:
        desvios = pd.DataFrame(linhas).sort_values("desvio")
        # Cada unidade se normaliza contra o proprio maximo: % de R$ e p.p. de
        # percentual nao dividem escala de cor.
        limites = {
            True: float(desvios[desvios["percentual"]]["desvio"].abs().max() or 1),
            False: float(desvios[~desvios["percentual"]]["desvio"].abs().max() or 1),
        }
        cores = [
            base.cor_divergente(
                linha["desvio"],
                direcao=theme.DIRECAO_KPI.get(DIRECAO[linha["tipo"]], "neutro"),
                limite=limites[bool(linha["percentual"])],
                tema=ctx.tema,
            )
            for _, linha in desvios.iterrows()
        ]
        textos = [
            fmt.pontos_percentuais(linha["desvio"]) if linha["percentual"]
            else fmt.variacao(linha["desvio"])
            for _, linha in desvios.iterrows()
        ]
        hover = [
            f"{rot.valor(linha['tipo'])}<br>"
            + (
                f"realizado {fmt.percentual(linha['realizado'], 2)}<br>"
                f"meta dos mesmos meses {fmt.percentual(linha['meta'], 2)}"
                if linha["percentual"]
                else f"realizado {fmt.moeda_compacta(linha['realizado'])}<br>"
                     f"meta dos mesmos meses {fmt.moeda_compacta(linha['meta'])}"
            )
            for _, linha in desvios.iterrows()
        ]
        fig = base.nova_figura(ctx.tema, altura=300, margin={"l": 230, "r": 110, "t": 16, "b": 48})
        base.barra_horizontal(
            fig, rot.valores(desvios["tipo"]), list(desvios["desvio"]),
            cores=cores, textos=textos, tema=ctx.tema, hover=hover,
        )
        fig.add_vline(x=0, line_width=1, line_color=t.eixo)
        fig.update_xaxes(
            title_text="Desvio contra a meta dos mesmos meses "
                       "(variação % nos indicadores em R$, pontos percentuais na inadimplência)",
            title_font_size=theme.TIPOGRAFIA["nota"],
        )
        base.mostrar_grafico(
            fig, chave="p1_desvio",
            nota="Azul é desvio favorável ao negócio: custo e inadimplência abaixo da meta contam "
                 "como favoráveis, ainda que o número seja negativo.",
            dados=comp,
            colunas_dados=["tipo_meta", "unidade", "realizado", "meta_alinhada", "meta_anual",
                           "variacao_abs_alinhada", "variacao_pct_alinhada", "periodo_realizado",
                           "versao_meta"],
        )

# --------------------------------------------------------------------------
# A meta foi cumprida em cada ano?
# --------------------------------------------------------------------------
ui.cabecalho_secao("A meta foi cumprida em cada ano?", ancora="conferencia")
# Analise temporal com o tempo na HORIZONTAL: uma coluna por exercicio, uma linha
# por indicador. O formato longo anterior (uma linha por indicador x ano) repetia
# o nome do indicador tres vezes e o ano cinco, e obrigava a caçar a comparacao
# ano a ano linha a linha.
linhas_matriz: list[dict[str, str]] = []
linhas_nivel: list[dict[str, str]] = []
cabecalhos: dict[int, str] = {}
for tipo in metas.TIPOS_META:
    linha: dict[str, str] = {"indicador": rot.valor(tipo)}
    nivel_linha: dict[str, str] = {"indicador": ""}
    for a in ANOS:
        df_ano = base.obter(dados, f"comp_{a}")
        reg = base.linha_meta(df_ano, tipo) if df_ano is not None else None
        if reg is None:
            linha[str(a)] = fmt.VAZIO
            nivel_linha[str(a)] = ""
            continue
        percentual = str(reg.get("unidade")) == "%"
        desvio = reg.get("variacao_abs_alinhada" if percentual else "variacao_pct_alinhada")
        d = fmt.delta(
            desvio,
            unidade="pp" if percentual else "pct",
            direcao=theme.DIRECAO_KPI.get(DIRECAO[tipo], "neutro"),
            ambar=ambar_inad if percentual else None,
            vermelho=vermelho_inad if percentual else None,
            tema=ctx.tema,
        )
        # Verde para o que bateu a meta, vermelho para o que nao bateu: a secao
        # pergunta "cumpriu?", que e binario. O nivel de `delta` respeita limiares
        # (e deixa em neutro o desvio pequeno sem regra), o que aqui deixaria em
        # cinza justamente as celulas que nao cumpriram. Onde ha limiar publicado
        # -- inadimplencia -- ele prevalece, para distinguir "estourou" de "passou".
        nivel = d.nivel
        if nivel == "neutro" and d.favoravel is not None:
            nivel = "bom" if d.favoravel else "critico"
        linha[str(a)] = f"{theme.ICONE_NIVEL[nivel]} {d.texto}".strip()
        nivel_linha[str(a)] = nivel
        meses = int(reg.get("meses_realizados") or 0)
        cabecalhos[a] = f"{a} · {meses} meses" if reg.get("eh_parcial") else str(a)
    linhas_matriz.append(linha)
    linhas_nivel.append(nivel_linha)

ui.matriz_status(
    pd.DataFrame(linhas_matriz),
    pd.DataFrame(linhas_nivel),
    colunas={"indicador": "Indicador", **{str(a): cabecalhos.get(a, str(a)) for a in ANOS}},
    ajudas={str(a): "Realizado contra a soma das metas dos mesmos meses do ano." for a in ANOS},
    tema=ctx.tema,
)
ui.nota_armadilha(
    "Cada célula é o desvio contra a meta dos mesmos meses do ano, não contra o "
    "orçamento do ano cheio."
)

# --------------------------------------------------------------------------
# Como o indicador andou mes a mes?
# --------------------------------------------------------------------------
ui.cabecalho_secao("Como cada indicador andou mês a mês?", ancora="mensal")


def _grafico_mensal(tipo: str, chave: str, *, altura: int, com_legenda: bool) -> None:
    """Serie mensal de um indicador contra a meta vigente.

    Os cinco indicadores ficam **todos na tela**, em vez de um seletor que troca o
    grafico: comparar faturamento com inadimplencia era impossivel quando so um
    aparecia por vez, e cada serie custa ~0,6 s (as cinco vao juntas no lote).
    """
    serie = base.obter(dados, f"serie_{tipo}")
    if serie is None:
        ui.erro_metrica(f"a série de {rot.valor(tipo)}", base.falhou(dados, f"serie_{tipo}"))
        return
    serie = serie[serie["realizado"].notna() | serie["meta"].notna()].copy()
    if serie.empty:
        ui.estado_vazio(f"Sem série de {rot.valor(tipo)} neste ano")
        return
    percentual = str(serie.iloc[0].get("unidade")) == "%"
    # Indicador em reais soma no balde; a inadimplencia e uma foto no ultimo dia,
    # entao o trimestre dela e o valor do ultimo mes, nunca a soma dos tres. E a
    # mesma regra que o orcamento usa (``tipo_agregacao = 'Fim de Periodo'``), que
    # e por isso que realizado e meta seguem juntos aqui.
    serie = base.reagrupar(
        serie, grao=grao,
        soma=[] if percentual else ["realizado", "meta"],
        fim=["realizado", "meta"] if percentual else [],
    )
    serie["variacao_abs"] = serie["realizado"] - serie["meta"]
    serie["x"] = base.datas_de(serie["ano_mes"])
    rotulos = {} if percentual else base.rotulos_de_barra(serie["realizado"])
    fig = base.nova_figura(ctx.tema, altura=altura)
    if percentual:
        fig.add_trace(
            go.Scatter(
                x=serie["x"], y=serie["realizado"], mode="lines+markers", name="Realizado",
                line={"color": theme.cor_indicador(tipo, ctx.tema), "width": theme.ESPESSURA_LINHA},
                marker={"size": theme.TAMANHO_MARCADOR},
                # O periodo do tooltip vem do rotulo do balde: fora do grao mensal a
                # marca fica ancorada no primeiro mes e a data do eixo mentiria.
                customdata=serie[["rotulo_periodo"]].to_numpy(),
                hovertemplate="%{customdata[0]}: <b>%{y:.2f}%</b><extra>Realizado</extra>",
            )
        )
    else:
        fig.add_trace(
            go.Bar(
                x=serie["x"], y=serie["realizado"], name="Realizado",
                marker={"color": theme.cor_indicador(tipo, ctx.tema),
                        "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
                # Rotulo direto em cada barra: dispensa ler o eixo para saber o valor.
                # Sem "R$" na marca: o titulo do eixo ja diz a unidade. O helper
                # devolve {} acima de 14 marcas, e ai o eixo volta a mostrar ticks.
                **rotulos,
                customdata=serie[["rotulo_periodo"]].to_numpy(),
                hovertemplate="%{customdata[0]}: R$ %{y:,.0f}<extra>Realizado</extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=serie["x"], y=serie["meta"], mode="lines", name="Meta vigente",
            line={"color": t.marca_meta, "width": theme.ESPESSURA_LINHA, "dash": "dash"},
            customdata=serie[["rotulo_periodo"]].to_numpy(),
            hovertemplate=("meta %{customdata[0]}: %{y:.2f}%<extra></extra>" if percentual
                           else "meta %{customdata[0]}: R$ %{y:,.0f}<extra></extra>"),
        )
    )
    if percentual:
        base.rotular_ultimo_ponto(
            fig, serie["x"], serie["realizado"],
            lambda v: fmt.percentual(v, 2),
            theme.cor_indicador(tipo, ctx.tema), tema=ctx.tema,
        )
    base.eixo_temporal(fig, serie, grao=grao)
    fig.update_yaxes(
        title_text=(f"% no fim {'do mês' if grao == 'mes' else base.NO_PERIODO[grao]}"
                    if percentual else f"R$ {base.NO_PERIODO[grao]}"),
        title_font_size=theme.TIPOGRAFIA["nota"],
        ticksuffix="%" if percentual else None,
        tickformat=None if percentual else ".2s",
        rangemode="tozero",
        # Onde cada marca traz o proprio numero, os ticks seriam a mesma leitura
        # pela regua. Onde o rotulo nao coube (muitos meses), o eixo volta -- do
        # contrario o grafico ficaria sem numero nenhum. O titulo fica sempre,
        # porque e ele que diz a unidade.
        showticklabels=not rotulos,
    )
    # Com legenda, o topo abriga duas linhas: titulo em cima, legenda logo abaixo.
    # Com margem de 46px as duas se sobrepunham e o nome do indicador se misturava
    # com "Realizado / Meta vigente".
    fig.update_layout(
        showlegend=com_legenda,
        legend=({"orientation": "h", "y": 1.13, "x": 0, "yanchor": "bottom"}
                if com_legenda else None),
        title={"text": rot.valor(tipo), "x": 0, "xanchor": "left", "y": 0.97,
               "yanchor": "top", "font": {"size": theme.TIPOGRAFIA["rotulo"]}},
        margin={"t": 84 if com_legenda else 46},
    )
    base.mostrar_grafico(fig, chave=chave, dados=serie.drop(columns=["x"]))


# Recebimento em largura inteira, nao faturamento: o dinheiro que **entrou** e o
# que decide o mes. Faturar e promessa; a leitura central do dataset e que
# faturamento e caixa vao bem e a crise e de credito -- e quem mostra o caixa e
# esta serie. Os outros quatro ficam em duas linhas de dois.
DESTAQUE = "Recebimento (Caixa)"
ORDEM_MENSAL = [DESTAQUE] + [t for t in metas.TIPOS_META if t != DESTAQUE]

_grafico_mensal(ORDEM_MENSAL[0], "p1_mensal_0", altura=300, com_legenda=True)
for a, b in ((1, 2), (3, 4)):
    # gap largo: em "medium" os quatro graficos encostavam uns nos outros e a
    # faixa parecia um bloco so.
    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        _grafico_mensal(ORDEM_MENSAL[a], f"p1_mensal_{a}", altura=250, com_legenda=False)
    with col_b:
        _grafico_mensal(ORDEM_MENSAL[b], f"p1_mensal_{b}", altura=250, com_legenda=False)
ui.nota_armadilha(
    "A inadimplência é o valor do último dia de cada mês, não a soma dos meses. "
    "Meses ainda sem realizado ficam vazios, nunca zerados."
)

# --------------------------------------------------------------------------
# Qual segmento explica o desvio?  (opcional -- e a consulta mais cara)
# --------------------------------------------------------------------------
ui.cabecalho_secao("Qual segmento explica o desvio?", ancora="segmento")
st.selectbox(
    "Indicador",
    options=[t for t in metas.TIPOS_META if t not in metas.SO_EMPRESA],
    format_func=rot.valor,
    key="meta_segmento_indicador",
    label_visibility="collapsed",
    help="Só os indicadores que têm meta por segmento aparecem aqui.",
)
if not tem_segmento:
    ui.bloco_desabilitado(
        f"{rot.valor(indicador)} só tem meta no nível Empresa: o custo de veículo parado não "
        "pertence a segmento nenhum, e por isso o orçamento não desce a esse nível.",
    )
else:
    ponte = base.obter(dados, "segmento")
    if ponte is None:
        ui.erro_metrica("a quebra por segmento", base.falhou(dados, "segmento"))
    else:
        ponte = ponte.copy()
        ponte["ordem"] = ponte["variacao_abs"].abs()
        ponte = ponte.sort_values("ordem", ascending=False)
        escala = theme.escala_divergente(ctx.tema)
        fig = base.nova_figura(ctx.tema, altura=380, hovermode="closest")
        fig.add_trace(
            go.Waterfall(
                orientation="v",
                measure=["absolute"] + ["relative"] * len(ponte) + ["total"],
                x=["Meta dos mesmos meses"] + rot.valores(ponte["segmento"]) + ["Realizado"],
                y=[float(ponte["meta_alinhada"].sum())]
                + [float(v) for v in ponte["variacao_abs"]] + [0.0],
                # Sem "R$" na marca: o eixo ja diz "R$ acumulado no periodo".
                text=[fmt.moeda_compacta(ponte["meta_alinhada"].sum(), prefixo=False)]
                + [fmt.moeda_compacta(v, com_sinal=True, prefixo=False)
                   for v in ponte["variacao_abs"]]
                + [fmt.moeda_compacta(ponte["realizado"].sum(), prefixo=False)],
                textposition="outside",
                textfont={"size": theme.TIPOGRAFIA["nota"], "color": t.tinta_secundaria},
                connector={"line": {"color": t.grade, "width": 1}},
                # Indices nomeados, nao literais: a escala ja mudou de tamanho
                # uma vez, e com literal isso teria quebrado em silencio.
                increasing={"marker": {"color": escala[theme.IDX_DIVERGENTE_FAVORAVEL]}},
                decreasing={"marker": {"color": escala[theme.IDX_DIVERGENTE_DESFAVORAVEL]}},
                totals={"marker": {"color": t.marca_neutro}},
                hovertemplate="%{x}<br>desvio: R$ %{y:,.0f}<extra></extra>",
            )
        )
        fig.update_yaxes(
            title_text="R$ acumulado no período", title_font_size=theme.TIPOGRAFIA["nota"],
            tickformat=".2s",
        )
        fig.update_xaxes(
            title_text="Segmento do cliente", title_font_size=theme.TIPOGRAFIA["nota"]
        )
        base.mostrar_grafico(
            fig, chave="p1_segmento",
            nota="A meta por segmento herda o mix do ano anterior: desvios grandes aqui são "
                 "composição do orçamento, não performance comercial. O sinal confiável é o total.",
            dados=ponte.drop(columns=["ordem"]),
        )

base.barra_qualidade(df_alertas, tema=ctx.tema)
