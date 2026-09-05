"""Pagina 2 -- Faturamento e Recebimento. "Quanto faturamos e quanto entrou em caixa?"

A correcao de premissa que a pagina existe para fazer: faturamento e caixa **nao
sao a mesma serie**. Eixos x semanticamente diferentes (competencia x data de
pagamento), por isso dois paineis empilhados e nunca eixo duplo.

Cancelamento perdeu a secao propria: virou **nota de rodape** do visual de
faturamento, alimentada por ``valor_cancelado`` / ``pct_cancelado``.

Deliberadamente fora: curva ABC (substituida pelo Top 10), mix por tipo de
receita como grafico (Locacao e ~96% -- e um rotulo, nao um donut) e MRR /
churn contratual, que sairam do escopo.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from frotas.metrics import credito, metas, receita
from frotas.ui import componentes as ui
from frotas.ui import format as fmt
from frotas.ui import rotulos as rot
from frotas.ui import theme
from views import _comum as base

PAGINA = 2

ctx = base.contexto()
base.abrir_pagina(ctx, "Quanto faturamos e quanto entrou em caixa?", secao="Faturamento e Recebimento", pagina=PAGINA)

t = theme.tokens(ctx.tema)
slot1 = theme.paleta_categorica(ctx.tema)[0]
f, ref, ano = ctx.filtros, ctx.data_ref, ctx.ano
f_yoy = f.com(competencia_ini=date(ano - 1, 1, 1), competencia_fim=f.fim)

with st.spinner("Apurando faturamento e caixa..."):
    dados = base.carregar(
        {
            "alertas": lambda: base.avaliar_alertas(f, ref, base.ALERTAS_DA_PAGINA[PAGINA]),
            "resumo": lambda: receita.resumo(f),
            "eficiencia": lambda: credito.eficiencia_cobranca(f, ref),
            "fat_comp": lambda: receita.faturamento_por_competencia(f),
            "caixa": lambda: metas.realizado_mensal("Recebimento (Caixa)"),
            "segmentos": lambda: receita.faturamento_por_dimensao(f, "segmento"),
            "yoy_mensal": lambda: receita.yoy_mensal(f_yoy),
            "yoy_anual": lambda: receita.yoy_anual(f_yoy),
            "top": lambda: receita.top_clientes(f, limite=10),
        }
    )

df_alertas = base.obter(dados, "alertas")
resumo = base.obter(dados, "resumo")
eficiencia = base.obter(dados, "eficiencia")


# --------------------------------------------------------------------------
# Faixa de KPIs
# --------------------------------------------------------------------------
piso_cobranca = base.limiares_de(df_alertas, "A4")[1]
janela_caixa = ""
if eficiencia is not None:
    ini = base.texto_celula(eficiencia, "janela_ini")
    fim = base.texto_celula(eficiencia, "janela_fim")
    if ini and fim:
        janela_caixa = fmt.periodo(ini, fim)

base.faixa_kpis(
    [
        {
            "rotulo": "Faturamento bruto",
            "valor": base.celula(resumo, "faturamento_bruto"),
            "unidade": "brl", "chave_direcao": "faturamento_bruto", "estado": "sem_meta",
            "nota": "antes de impostos",
            "ajuda": "Somado pelo mês de competência (o mês do serviço), não pela data de emissão.",
        },
        {
            "rotulo": "Receita líquida",
            "valor": base.celula(resumo, "receita_liquida"),
            "unidade": "brl", "chave_direcao": "receita_liquida", "estado": "sem_meta",
            "nota": f"impostos: {fmt.moeda_compacta(base.celula(resumo, 'impostos'))}",
            "ajuda": "Faturamento menos impostos, incluindo faturas canceladas. É a definição publicada.",
        },
        {
            "rotulo": "Recebimento em 12 meses",
            "valor": base.celula(eficiencia, "recebimento_12m"),
            "unidade": "brl", "chave_direcao": "recebimento_caixa", "estado": "sem_meta",
            "nota": f"caixa de {janela_caixa}" if janela_caixa else None,
            "badges": ["Janela de 12 meses"],
            "ajuda": "Somado pela data de pagamento, com juros e multa. Não soma com o "
                     "faturamento do mesmo mês.",
        },
        {
            "rotulo": "Eficiência de cobrança",
            "valor": base.celula(eficiencia, "eficiencia_pct"),
            "unidade": "pct", "casas": 1, "chave_direcao": "eficiencia_cobranca",
            "estado": "sem_meta",
            "nota": (f"piso da meta: {fmt.percentual(piso_cobranca, 1)}"
                     if piso_cobranca is not None else None),
            "badges": ["Janela de 12 meses"],
            "ajuda": "Caixa recebido dividido pelo faturamento válido, ambos na mesma janela "
                     "de 12 meses.",
        },
        {
            "rotulo": "Ticket médio",
            "valor": base.celula(resumo, "ticket_medio"),
            "unidade": "brl", "chave_direcao": "ticket_medio", "estado": "sem_meta",
            "nota": f"{fmt.contagem(base.celula(resumo, 'qtd_titulos'))} faturas",
            "ajuda": "Faturamento bruto dividido pela quantidade de faturas do período.",
        },
    ],
    tema=ctx.tema,
)

ui.banner_alerta(
    base.alertas_da_pagina(df_alertas, PAGINA, destinos={"A1": base.ROTAS[3],
                                                         "A6": base.ROTAS[4]}),
    maximo=3, tema=ctx.tema,
    regras_avaliadas=base.regras_da_pagina(df_alertas, PAGINA),
    estado="erro" if df_alertas is None else "normal", data_ref=ref,
)

ui.nota_armadilha(
    "Faturamento e caixa não somam e nunca dividem eixo: um é contado pelo mês de competência, "
    "o outro pela data em que o dinheiro entrou. A defasagem típica entre os dois é de 1 a 3 meses."
)

# --------------------------------------------------------------------------
# As duas series, lado a lado no tempo
# --------------------------------------------------------------------------
ui.cabecalho_secao("O caixa acompanha o que foi faturado?", ancora="series")
fat = base.obter(dados, "fat_comp")
caixa = base.obter(dados, "caixa")
if fat is None:
    ui.erro_metrica("o faturamento por competência", base.falhou(dados, "fat_comp"))
else:
    meses = list(fat["ano_mes"])
    if caixa is not None:
        caixa = caixa[caixa["ano_mes"].isin(meses)]
    teto = base.maximo_da_coluna(fat, "faturamento_bruto")
    if caixa is not None and not caixa.empty:
        teto = max(teto, base.maximo_da_coluna(caixa, "realizado"))
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.18,
        subplot_titles=("Faturamento bruto, por competência", "Recebimento, por data de pagamento"),
    )
    fig.add_trace(
        go.Bar(
            x=base.datas_de(meses), y=fat["faturamento_bruto"], name="Faturamento bruto",
            marker={"color": slot1,
                    "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
            hovertemplate="competência %{x|%b/%Y}: R$ %{y:,.0f}<extra></extra>",
        ),
        row=1, col=1,
    )
    if caixa is not None and not caixa.empty:
        fig.add_trace(
            go.Bar(
                x=base.datas_de(caixa["ano_mes"]), y=caixa["realizado"], name="Recebimento",
                marker={"color": slot1,
                        "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
                hovertemplate="caixa %{x|%b/%Y}: R$ %{y:,.0f}<extra></extra>",
            ),
            row=2, col=1,
        )
    fig.update_layout(**theme.layout_grafico(ctx.tema))
    fig.update_layout(height=390, showlegend=False, hovermode="x unified", bargap=0.25)
    for linha, titulo in ((1, "Mês de competência"), (2, "Mês do pagamento")):
        fig.update_xaxes(
            tickmode="array", tickvals=base.datas_de(meses), ticktext=base.rotulos_mensais(meses),
            title_text=titulo, title_font_size=theme.TIPOGRAFIA["nota"],
            gridcolor=t.grade, linecolor=t.eixo, row=linha, col=1,
        )
        fig.update_yaxes(
            title_text="R$ no mês", title_font_size=theme.TIPOGRAFIA["nota"], tickformat=".2s",
            range=[0, teto * 1.1 if teto else 1], gridcolor=t.grade, linecolor=t.eixo,
            row=linha, col=1,
        )
    for anotacao in fig.layout.annotations:
        anotacao.font.size = theme.TIPOGRAFIA["nota"]
        anotacao.font.color = t.tinta_secundaria

    cancelado = base.celula(resumo, "valor_cancelado")
    pct_cancelado = base.celula(resumo, "pct_cancelado")
    partes_nota = []
    if cancelado is not None:
        partes_nota.append(
            f"Cancelamentos no período: {fmt.moeda_compacta(cancelado)} "
            f"({fmt.percentual(pct_cancelado, 2)} do faturado), avaliados na data de referência "
            f"(uma fatura cancelada depois dela ainda conta como faturamento)."
        )
    if ctx.tem_recorte:
        partes_nota.append(
            "O caixa mensal é sempre o da empresa: não existe série de recebimento por recorte "
            "de cliente."
        )
    base.mostrar_grafico(
        fig, chave="p2_series", nota=" ".join(partes_nota) or None,
        dados=fat,
        colunas_dados=["ano_mes", "faturamento_bruto", "faturamento_valido", "receita_liquida",
                       "impostos", "valor_cancelado", "qtd_titulos"],
    )

# --------------------------------------------------------------------------
# Quem paga a conta?  |  Crescemos sobre o ano passado?
# --------------------------------------------------------------------------
col_seg, col_yoy = st.columns([6, 6], gap="medium")

with col_seg:
    ui.cabecalho_secao("Quem paga a conta?")
    seg = base.obter(dados, "segmentos")
    if seg is None:
        ui.erro_metrica("o faturamento por segmento", base.falhou(dados, "segmentos"))
    else:
        seg = seg.sort_values("faturamento_bruto", ascending=False)
        fig = base.nova_figura(ctx.tema, altura=340, margin={"l": 180, "r": 100, "t": 16, "b": 48})
        base.barra_horizontal(
            fig,
            rot.valores(seg["segmento"]),
            list(seg["faturamento_bruto"]),
            cores=[theme.cor_segmento(s, ctx.tema) for s in seg["segmento"]],
            textos=[f"{fmt.percentual(p, 1)}  {fmt.moeda_compacta(v)}"
                    for p, v in zip(seg["participacao_pct"], seg["faturamento_bruto"])],
            tema=ctx.tema,
            hover=[f"{rot.valor(s)}<br>{fmt.moeda(v)}<br>{fmt.percentual(p, 1)} do faturamento"
                   for s, v, p in zip(seg["segmento"], seg["faturamento_bruto"],
                                      seg["participacao_pct"])],
        )
        fig.update_xaxes(
            title_text="R$ faturado no período", title_font_size=theme.TIPOGRAFIA["nota"],
            tickformat=".2s",
        )
        base.mostrar_grafico(fig, chave="p2_segmentos", dados=seg)

with col_yoy:
    ui.cabecalho_secao("Crescemos sobre o ano passado?")
    yoy = base.obter(dados, "yoy_mensal")
    if yoy is None:
        ui.erro_metrica("a comparação com o ano anterior", base.falhou(dados, "yoy_mensal"))
    else:
        yoy = yoy[yoy["ano"] == ano].sort_values("ano_mes")
        anterior = pd.to_numeric(yoy["faturamento_bruto_ano_anterior"], errors="coerce")
        fig = base.nova_figura(ctx.tema, altura=340)
        fig.add_trace(
            go.Bar(
                x=base.datas_de(yoy["ano_mes"]), y=anterior, name=f"{ano - 1}",
                marker={"color": theme.TRANSPARENTE,
                        "line": {"color": t.marca_neutro, "width": 1.5}},
                hovertemplate=f"{ano - 1} %{{x|%b}}: R$ %{{y:,.0f}}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Bar(
                x=base.datas_de(yoy["ano_mes"]), y=yoy["faturamento_bruto"], name=f"{ano}",
                marker={"color": slot1, "line": {"color": t.superficie, "width": 1}},
                hovertemplate=f"{ano} %{{x|%b}}: R$ %{{y:,.0f}}<extra></extra>",
            )
        )
        base.eixo_mensal(fig, list(yoy["ano_mes"]))
        fig.update_yaxes(
            title_text="R$ por competência", title_font_size=theme.TIPOGRAFIA["nota"],
            tickformat=".2s", rangemode="tozero",
        )
        fig.update_layout(
            barmode="group", showlegend=True, legend={"orientation": "h", "y": 1.15, "x": 0},
            bargap=0.3, bargroupgap=0.05,
        )
        anual = base.obter(dados, "yoy_anual")
        comparavel = None
        if anual is not None and "ano" in anual.columns:
            linha = anual[anual["ano"] == ano]
            if not linha.empty:
                comparavel = linha.iloc[0].get("variacao_pct_comparavel")
        base.mostrar_grafico(
            fig, chave="p2_yoy",
            nota=(f"No acumulado, {fmt.variacao(comparavel)} contra os mesmos meses de {ano - 1} "
                  ". Comparar com o ano cheio anterior subestimaria um ano parcial."
                  if not fmt.eh_vazio(comparavel) else None),
            dados=yoy,
            colunas_dados=["ano_mes", "faturamento_bruto", "faturamento_bruto_ano_anterior",
                           "variacao_abs", "variacao_pct"],
        )

# --------------------------------------------------------------------------
# Os dez maiores clientes
# --------------------------------------------------------------------------
ui.cabecalho_secao("Quais clientes concentram o faturamento?", ancora="clientes")
top = base.obter(dados, "top")
if top is not None:
    top = top.assign(
        segmento=top["segmento"].map(rot.valor),
        porte=top["porte"].map(rot.valor),
    )
ui.tabela_com_barra(
    top if top is not None else pd.DataFrame(),
    colunas={
        "nome_cliente": ui.ColunaSpec("Cliente", "texto", largura="large"),
        "segmento": ui.ColunaSpec("Segmento", "texto", largura="medium"),
        "porte": ui.ColunaSpec("Porte", "texto", largura="small"),
        "rating_credito": ui.ColunaSpec("Rating de crédito", "texto", largura="small"),
        "faturamento_bruto": ui.ColunaSpec("Faturamento bruto", "brl_compacto"),
        "receita_liquida": ui.ColunaSpec("Receita líquida", "brl_compacto"),
        "qtd_titulos": ui.ColunaSpec("Faturas", "num", largura="small"),
        "participacao_pct": ui.ColunaSpec("Participação", "pct", casas=2),
    },
    barra="faturamento_bruto",
    rotulo_barra="Faturamento bruto",
    escala="neutra",
    ordenar_por="faturamento_bruto",
    limite=10,
    chave="p2_top_clientes",
    tema=ctx.tema,
    estado="erro" if top is None and base.falhou(dados, "top") else "normal",
    vazio_corpo="Os filtros ativos não retornaram faturamento no período selecionado.",
)

base.barra_qualidade(df_alertas, tema=ctx.tema)
