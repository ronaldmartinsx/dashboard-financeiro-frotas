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
# Cor do indicador que a pagina trata (ver theme.INDICADORES).
slot1 = theme.cor_indicador("Faturamento", ctx.tema)
f, ref, ano = ctx.filtros, ctx.data_ref, ctx.ano
f_yoy = f.com(competencia_ini=date(ano - 1, 1, 1), competencia_fim=f.fim)

with st.spinner("Apurando faturamento e caixa..."):
    dados = base.carregar(
        {
            "alertas": lambda: base.avaliar_alertas(f, ref, base.ALERTAS_DA_PAGINA[PAGINA]),
            "resumo": lambda: receita.resumo(f),
            "cobertura": lambda: credito.cobertura_de_caixa(f, ref),
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
cobertura = base.obter(dados, "cobertura")


# --------------------------------------------------------------------------
# Faixa de KPIs
# --------------------------------------------------------------------------
piso_cobranca = base.limiares_de(df_alertas, "A4")[1]
janela_caixa = ""
if cobertura is not None:
    ini = base.texto_celula(cobertura, "janela_ini")
    fim = base.texto_celula(cobertura, "janela_fim")
    if ini and fim:
        janela_caixa = fmt.periodo(ini, fim)
faturado = base.celula(resumo, "faturamento_bruto")
impostos = base.celula(resumo, "impostos")

base.faixa_kpis(
    [
        {
            "rotulo": "Faturamento bruto",
            "valor": faturado,
            "unidade": "brl", "chave_direcao": "faturamento_bruto", "estado": "sem_meta",
            "nota": f"receita líquida: {fmt.moeda_compacta(base.celula(resumo, 'receita_liquida'))}",
            "ajuda": "Somado pelo mês de competência (o mês do serviço), não pela data de emissão. "
                     "A receita líquida é o mesmo valor já sem impostos.",
        },
        {
            "rotulo": "Impostos sobre a receita",
            "valor": impostos,
            "unidade": "brl", "chave_direcao": "impostos", "estado": "sem_meta",
            "nota": (f"{fmt.percentual(100.0 * impostos / faturado, 2)} do faturado"
                     if not fmt.eh_vazio(impostos) and faturado else None),
            "ajuda": "Alíquota de 3,65% na locação pura e 8,65% quando o contrato tem serviço "
                     "ou motorista, por isso o percentual varia com o mix.",
        },
        {
            "rotulo": "Recebimento em 12 meses",
            "valor": base.celula(cobertura, "recebimento_12m"),
            "unidade": "brl", "chave_direcao": "recebimento_caixa", "estado": "sem_meta",
            "nota": f"caixa de {janela_caixa}" if janela_caixa else None,
            "ajuda": "Somado pela data de pagamento, sem juros e multa. Não soma com o "
                     "faturamento do mesmo mês.",
        },
        {
            "rotulo": "Cobertura de caixa",
            "valor": base.celula(cobertura, "cobertura_pct"),
            "unidade": "pct", "casas": 1, "chave_direcao": "cobertura_caixa",
            "estado": "sem_meta",
            "nota": (f"piso da meta: {fmt.percentual(piso_cobranca, 1)}"
                     if piso_cobranca is not None else None),
            "ajuda": "Quanto do faturado dos últimos 12 meses já virou caixa no mesmo intervalo. "
                     "Não mede eficiência de cobrança: o caixa de um mês vem do faturamento de "
                     "1 a 3 meses antes, então crescer no faturamento derruba a razão.",
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
    # Um grafico so: barras do faturado e linha tracejada do recebido. Os dois
    # sao R$ na mesma escala, entao dividem o eixo sem distorcer -- e e justamente
    # a distancia entre a barra e a linha que interessa. O empilhado anterior
    # obrigava o olho a saltar entre dois paineis para comparar o mesmo mes.
    rotulos_fat = base.rotulos_de_barra(fat["faturamento_bruto"])
    fig = base.nova_figura(ctx.tema, altura=380)
    fig.add_trace(
        go.Bar(
            x=base.datas_de(meses), y=fat["faturamento_bruto"], name="Faturado",
            marker={"color": theme.cor_indicador("Faturamento", ctx.tema),
                    "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
            **rotulos_fat,
            hovertemplate="competência %{x|%b/%Y}: R$ %{y:,.0f}<extra>Faturado</extra>",
        )
    )
    if caixa is not None and not caixa.empty:
        fig.add_trace(
            go.Scatter(
                x=base.datas_de(caixa["ano_mes"]), y=caixa["realizado"],
                mode="lines+markers", name="Recebido",
                # Preto (a tinta do tema), nao a cor do indicador: sobre as barras
                # azuis o aqua nao destacava. A linha e a referencia de leitura.
                line={"color": t.tinta, "width": theme.ESPESSURA_LINHA, "dash": "dash"},
                marker={"size": theme.TAMANHO_MARCADOR, "color": t.tinta},
                hovertemplate="pago em %{x|%b/%Y}: R$ %{y:,.0f}<extra>Recebido</extra>",
            )
        )
        base.rotular_ultimo_ponto(
            fig, base.datas_de(caixa["ano_mes"]), caixa["realizado"],
            fmt.moeda_compacta(caixa["realizado"].iloc[-1]), t.tinta, tema=ctx.tema,
        )
    base.eixo_mensal(fig, meses)
    fig.update_yaxes(
        title_text="R$ no mês", title_font_size=theme.TIPOGRAFIA["nota"],
        tickformat=".2s", range=[0, teto * 1.15 if teto else 1],
        # Com rotulo em cada barra o eixo repetiria a leitura; sem ele (muitos
        # meses), o eixo volta a ser a unica referencia.
        showticklabels=not rotulos_fat,
    )
    fig.update_layout(
        hovermode="x unified", bargap=0.25,
        showlegend=True, legend={"orientation": "h", "y": 1.14, "x": 0},
    )

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
            # Uma cor so: o segmento e o eixo, ja rotulado em cada barra. Oito matizes
            # aqui competiam com as cores dos indicadores, que sao as que atravessam
            # o relatorio inteiro.
            cores=[theme.cor_indicador("Faturamento", ctx.tema)] * len(seg),
            # Sem "R$" na marca: o eixo ja diz "R$ faturado no periodo".
            textos=[f"{fmt.percentual(p, 1)}  {fmt.moeda_compacta(v, prefixo=False)}"
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
        "nome_cliente": ui.ColunaSpec("Cliente", "texto"),
        "segmento": ui.ColunaSpec("Segmento", "texto"),
        "porte": ui.ColunaSpec("Porte", "texto"),
        "rating_credito": ui.ColunaSpec("Rating", "texto"),
        "faturamento_bruto": ui.ColunaSpec("Faturamento bruto", "brl_compacto"),
        "participacao_pct": ui.ColunaSpec("Participação", "pct", casas=2),
    },
    # Mesma escala de rating da pagina de inadimplencia: a celula inteira vira a
    # marca (A verde ... D vermelho). Um cliente grande com rating D e exatamente
    # o que esta tabela existe para mostrar.
    pintar_fundo=(
        {"rating_credito": [theme.RATING_NIVEL.get(str(r).strip().upper(), "neutro")
                            for r in top["rating_credito"]]}
        if top is not None and "rating_credito" in top.columns else None
    ),
    barra="faturamento_bruto",
    rotulo_barra="Peso",
    escala="neutra",
    ordenar_por="faturamento_bruto",
    limite=10,
    chave="p2_top_clientes",
    tema=ctx.tema,
    estado="erro" if top is None and base.falhou(dados, "top") else "normal",
    vazio_corpo="Os filtros ativos não retornaram faturamento no período selecionado.",
)

base.barra_qualidade(df_alertas, tema=ctx.tema)
