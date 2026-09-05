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
base.abrir_pagina(ctx, "Estamos entregando a meta?")

t = theme.tokens(ctx.tema)
f, ref, ano = ctx.filtros, ctx.data_ref, ctx.ano
ANOS = list(range(config.COMPETENCIA_MIN.year, config.COMPETENCIA_MAX.year + 1))

# Widgets sao lidos do estado **antes** do carregamento: sao eles que decidem
# quais consultas entram no lote. Os proprios widgets aparecem la embaixo, na
# secao a que pertencem -- por isso o estado nasce aqui, e nao no widget.
if st.session_state.get("meta_indicador") not in metas.TIPOS_META:
    st.session_state["meta_indicador"] = metas.TIPOS_META[0]
st.session_state.setdefault("meta_por_segmento", False)
indicador = st.session_state["meta_indicador"]
ver_segmento = bool(st.session_state["meta_por_segmento"])
tem_segmento = indicador not in metas.SO_EMPRESA

tarefas: dict = {}
if ver_segmento and tem_segmento:
    # Primeiro no lote de proposito: e a consulta mais cara da pagina (~13 s) e
    # precisa comecar junto com as outras, nao depois delas.
    tarefas["segmento"] = lambda: metas.comparativo_por_segmento(indicador, ano)
tarefas.update(
    {
        "serie": lambda: metas.serie_mensal(indicador, ano),
        "alertas": lambda: base.avaliar_alertas(f, ref, base.ALERTAS_DA_PAGINA[PAGINA]),
    }
)
for a in ANOS:
    tarefas[f"comp_{a}"] = lambda alvo=a: metas.comparativo_anual(alvo)

with st.spinner("Apurando realizado e meta..."):
    dados = base.carregar(tarefas, trabalhadores=6)

df_alertas = base.obter(dados, "alertas")
comp = base.obter(dados, f"comp_{ano}")

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
    janela = base.texto_periodo(reg.get("periodo_realizado")) if reg is not None else ""
    meta_alinhada = None if reg is None else reg.get("meta_alinhada")
    if reg is None:
        rodape_meta = None
        contexto_anual = None
    elif percentual:
        rodape_meta = f"vs. meta {janela} = {fmt.percentual(meta_alinhada, 2)}"
        contexto_anual = f"ano cheio: {fmt.pontos_percentuais(reg.get('variacao_abs_anual'))}"
    else:
        rodape_meta = f"vs. meta {janela} = {fmt.moeda_compacta(meta_alinhada)}"
        contexto_anual = f"meta do ano cheio: {fmt.moeda_compacta(reg.get('meta_anual'))}"
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

if parcial:
    ui.nota_armadilha(
        f"{ano} tem {int(comp.iloc[0]['meses_realizados'])} meses de realizado. Toda comparação "
        "desta página usa a soma das metas dos mesmos meses; contra o orçamento do ano cheio o "
        "desvio de faturamento sairia em −31%, que não é performance, é calendário."
    )

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
conferencia = []
for a in ANOS:
    df_ano = base.obter(dados, f"comp_{a}")
    if df_ano is None:
        continue
    for tipo in metas.TIPOS_META:
        reg = base.linha_meta(df_ano, tipo)
        if reg is None:
            continue
        percentual = str(reg.get("unidade")) == "%"
        desvio = reg.get("variacao_abs_alinhada" if percentual else "variacao_pct_alinhada")
        meses = int(reg.get("meses_realizados") or 0)
        conferencia.append(
            {
                "indicador": rot.valor(tipo),
                "exercicio": f"{a} · {meses} meses" if reg.get("eh_parcial") else str(a),
                "realizado": fmt.percentual(reg["realizado"], 2) if percentual
                else fmt.moeda_compacta(reg["realizado"]),
                "meta": fmt.percentual(reg.get("meta_alinhada"), 2) if percentual
                else fmt.moeda_compacta(reg.get("meta_alinhada")),
                "desvio": fmt.pontos_percentuais(desvio) if percentual else fmt.variacao(desvio),
                "orcamento": rot.valor(reg.get("versao_meta")),
                "magnitude": abs(float(desvio)) if not fmt.eh_vazio(desvio) else 0.0,
            }
        )
ui.tabela_com_barra(
    pd.DataFrame(conferencia),
    colunas={
        "indicador": ui.ColunaSpec("Indicador", "texto", largura="medium"),
        "exercicio": ui.ColunaSpec("Exercício", "texto", largura="small"),
        "realizado": ui.ColunaSpec("Realizado", "texto"),
        "meta": ui.ColunaSpec("Meta dos mesmos meses", "texto"),
        "desvio": ui.ColunaSpec(
            "Desvio", "texto",
            ajuda="Indicador em R$ lê variação percentual; indicador em % lê pontos percentuais.",
        ),
        "orcamento": ui.ColunaSpec("Versão do orçamento", "texto", largura="medium"),
    },
    barra="magnitude",
    rotulo_barra="Tamanho do desvio",
    escala="divergente",
    ordenar_por=None,
    limite=None,
    chave="p1_conferencia",
    tema=ctx.tema,
    vazio_titulo="Nenhum ano com meta apurada",
)

# --------------------------------------------------------------------------
# Como o indicador andou mes a mes?
# --------------------------------------------------------------------------
ui.cabecalho_secao("Como o indicador andou mês a mês?", ancora="mensal")
st.segmented_control(
    "Indicador orçado",
    options=list(metas.TIPOS_META),
    format_func=rot.valor,
    selection_mode="single",
    key="meta_indicador",
    label_visibility="collapsed",
    help="Os cinco indicadores com orçamento vigente neste projeto.",
)
serie = base.obter(dados, "serie")
if serie is None:
    ui.erro_metrica("o acompanhamento mensal", base.falhou(dados, "serie"))
else:
    serie = serie[serie["realizado"].notna() | serie["meta"].notna()].copy()
    percentual = str(serie.iloc[0].get("unidade")) == "%"
    serie["x"] = base.datas_de(serie["ano_mes"])
    fig = base.nova_figura(ctx.tema, altura=330)
    if percentual:
        fig.add_trace(
            go.Scatter(
                x=serie["x"], y=serie["realizado"], mode="lines+markers", name="Realizado",
                line={"color": t.marca_critico, "width": theme.ESPESSURA_LINHA},
                marker={"size": theme.TAMANHO_MARCADOR},
                hovertemplate="%{x|%b/%Y}: <b>%{y:.2f}%</b><extra>Realizado</extra>",
            )
        )
    else:
        fig.add_trace(
            go.Bar(
                x=serie["x"], y=serie["realizado"], name="Realizado",
                marker={"color": theme.paleta_categorica(ctx.tema)[0],
                        "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
                hovertemplate="%{x|%b/%Y}: R$ %{y:,.0f}<extra>Realizado</extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=serie["x"], y=serie["meta"], mode="lines", name="Meta vigente",
            line={"color": t.marca_meta, "width": theme.ESPESSURA_LINHA, "dash": "dash"},
            hovertemplate=("meta %{x|%b/%Y}: %{y:.2f}%<extra></extra>" if percentual
                           else "meta %{x|%b/%Y}: R$ %{y:,.0f}<extra></extra>"),
        )
    )
    base.eixo_mensal(fig, list(serie["ano_mes"]))
    fig.update_yaxes(
        title_text="% no fim do mês" if percentual else "R$ no mês",
        title_font_size=theme.TIPOGRAFIA["nota"],
        ticksuffix="%" if percentual else None,
        tickformat=None if percentual else ".2s",
        rangemode="tozero",
    )
    fig.update_layout(showlegend=True, legend={"orientation": "h", "y": 1.15, "x": 0})
    base.mostrar_grafico(
        fig, chave="p1_mensal",
        nota=("O valor do mês é a foto do último dia — inadimplência não se soma."
              if percentual else
              "Meses ainda sem realizado ficam vazios, nunca zerados."),
        dados=serie.drop(columns=["x"]),
    )

# --------------------------------------------------------------------------
# Qual segmento explica o desvio?  (opcional -- e a consulta mais cara)
# --------------------------------------------------------------------------
ui.cabecalho_secao("Qual segmento explica o desvio?", ancora="segmento")
st.toggle(
    "Abrir a quebra por segmento",
    key="meta_por_segmento",
    disabled=not tem_segmento,
    help="Custa cerca de 13 s: são oito segmentos apurados um a um. Custo Operacional e "
         "Inadimplência não têm meta por segmento — o custo de veículo parado não pertence "
         "a segmento nenhum.",
)
if not tem_segmento:
    ui.bloco_desabilitado(
        f"{rot.valor(indicador)} só tem meta no nível Empresa: o custo de veículo parado não "
        "pertence a segmento nenhum, e por isso o orçamento não desce a esse nível.",
    )
elif not ver_segmento:
    ui.estado_vazio(
        "Quebra por segmento fechada",
        "Ligue o botão acima para apurar os oito segmentos.",
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
                text=[fmt.moeda_compacta(ponte["meta_alinhada"].sum())]
                + [fmt.moeda_compacta(v, com_sinal=True) for v in ponte["variacao_abs"]]
                + [fmt.moeda_compacta(ponte["realizado"].sum())],
                textposition="outside",
                textfont={"size": theme.TIPOGRAFIA["nota"], "color": t.tinta_secundaria},
                connector={"line": {"color": t.grade, "width": 1}},
                increasing={"marker": {"color": escala[5]}},
                decreasing={"marker": {"color": escala[1]}},
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
base.rodape(ctx)
