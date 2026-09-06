"""Pagina 4 -- Custos. "Para onde vai o custo?"

Composicao (categoria e natureza), sazonalidade e o peso do veiculo parado.

Desvio consciente do pedido original: a serie de ociosidade foi pedida com
**duplo eixo** (veiculos parados x custo) e esta aqui como **dois paineis
empilhados com o mesmo eixo x**. Eixo duplo e o erro n.1 de dataviz -- a
intersecao das curvas nao significa nada.

Deliberadamente fora: margem operacional (saiu do projeto por completo),
corretiva por faixa de idade e por veiculo recorrente, e qualquer recorte de
ociosidade por cliente ou contrato -- veiculo parado nao tem a quem ser
atribuido.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frotas.metrics import custos
from frotas.ui import componentes as ui
from frotas.ui import format as fmt
from frotas.ui import rotulos as rot
from frotas.ui import theme
from views import _comum as base

PAGINA = 4
CATEGORIA_OCIOSA = "Patio e Ociosidade"

ctx = base.contexto()
base.abrir_pagina(ctx, "Para onde vai o custo?", secao="Custos", pagina=PAGINA)

t = theme.tokens(ctx.tema)
# Cor do indicador que a pagina trata (ver theme.INDICADORES).
slot1 = theme.cor_indicador("Custo Operacional", ctx.tema)
f, ref = ctx.filtros, ctx.data_ref
# Armadilha 6: veiculo parado tem contrato nulo. Com recorte de cliente ou de
# contrato o bloco fica **desabilitado**, nunca zerado.
sem_ociosidade = bool(f.tem_recorte_cliente or f.tipos_contrato or f.status_contrato)

tarefas = {
    "alertas": lambda: base.avaliar_alertas(f, ref, base.ALERTAS_DA_PAGINA[PAGINA]),
    "mensal": lambda: custos.custos_por_competencia(f),
    "categorias": lambda: custos.custos_por_dimensao(f, "categoria_custo"),
    "naturezas": lambda: custos.custos_por_dimensao(f, "tipo_custo"),
    "por_veiculo": lambda: custos.custos_por_dimensao(f, "categoria_veiculo"),
}
if not sem_ociosidade:
    tarefas["ociosidade"] = lambda: custos.custo_ociosidade(f)

with st.spinner("Apurando o custo operacional..."):
    dados = base.carregar(tarefas)

df_alertas = base.obter(dados, "alertas")
mensal = base.obter(dados, "mensal")


# --------------------------------------------------------------------------
# Faixa de KPIs
# --------------------------------------------------------------------------
escopo_contratos = bool(
    mensal is not None and not bool(mensal.iloc[0].get("custo_ocioso_incluido", True))
)
badges_escopo = ["escopo: contratos"] if escopo_contratos else []
custo_total = base.soma(mensal, "custo_total")


def _peso(valor: float | None) -> str | None:
    if valor is None or not custo_total:
        return None
    return f"{fmt.percentual(valor / custo_total * 100, 1)} do custo"


custo_fixo = base.soma(mensal, "custo_fixo")
custo_variavel = base.soma(mensal, "custo_variavel")
custo_nao_caixa = base.soma(mensal, "custo_nao_caixa")
custo_ocioso = base.soma(mensal, "custo_ocioso")

base.faixa_kpis(
    [
        {
            "rotulo": "Custo de contratos" if escopo_contratos else "Custo operacional",
            "valor": custo_total, "unidade": "brl", "chave_direcao": "custo_operacional",
            "estado": "sem_meta" if custo_total is not None else "erro",
            "nota": None,
            "badges": badges_escopo,
            "ajuda": "Todo o custo do período, com depreciação e com o veículo parado. Com "
                     "recorte de cliente ou de contrato só entra o custo alocado a contrato.",
        },
        {
            "rotulo": "Custo fixo", "valor": custo_fixo, "unidade": "brl",
            "chave_direcao": "custo_operacional", "estado": "sem_meta",
            "nota": _peso(custo_fixo), "badges": badges_escopo,
            "ajuda": "Custo que não acompanha o uso da frota: seguro, motorista, overhead.",
        },
        {
            "rotulo": "Custo variável", "valor": custo_variavel, "unidade": "brl",
            "chave_direcao": "custo_operacional", "estado": "sem_meta",
            "nota": _peso(custo_variavel), "badges": badges_escopo,
            "ajuda": "Custo que acompanha o uso: manutenção, pneus, combustível de pátio.",
        },
        {
            "rotulo": "Custo não caixa", "valor": custo_nao_caixa, "unidade": "brl",
            "chave_direcao": "custo_operacional", "estado": "sem_meta",
            "nota": _peso(custo_nao_caixa), "badges": badges_escopo,
            "ajuda": "Depreciação: entra no resultado, não sai do caixa.",
        },
        {
            "rotulo": "Custo de veículo parado",
            "valor": None if escopo_contratos else custo_ocioso, "unidade": "brl",
            "chave_direcao": "custo_ociosidade",
            "estado": "sem_dado" if escopo_contratos else "sem_meta",
            "nota": ("fora do escopo: veículo parado não tem cliente"
                     if escopo_contratos else _peso(custo_ocioso)),
            "badges": badges_escopo,
            "ajuda": "Custo das linhas sem contrato: pátio, seguro e depreciação do veículo "
                     "que não está alocado.",
        },
    ],
    tema=ctx.tema,
)

ui.banner_alerta(
    base.alertas_da_pagina(df_alertas, PAGINA),
    maximo=3, tema=ctx.tema,
    regras_avaliadas=base.regras_da_pagina(df_alertas, PAGINA),
    estado="erro" if df_alertas is None else "normal", data_ref=ref,
)

if escopo_contratos:
    ui.nota_armadilha(
        "O recorte ativo troca a fonte do custo: sai o pátio, fica só o custo alocado a contrato. "
        "O total encolhe e deixa de ser comparável com o orçamento, por isso o indicador mudou "
        "de nome e a comparação com a meta some.",
        tom="aviso",
    )
else:
    ui.nota_armadilha(
        "O custo aqui é o da empresa e inclui o veículo parado, que não pertence a cliente nem a "
        "segmento. Qualquer recorte de cliente ou de contrato troca a fonte para o custo alocado "
        "e o pátio desaparece da conta."
    )

# --------------------------------------------------------------------------
# Como o custo se comporta ao longo do ano?
# --------------------------------------------------------------------------
ui.cabecalho_secao("Como o custo se comporta ao longo do ano?", ancora="mensal")
if mensal is None:
    ui.erro_metrica("a série mensal de custo", base.falhou(dados, "mensal"))
else:
    meses = list(mensal["ano_mes"])
    rotulos_custo = base.rotulos_de_barra(mensal["custo_total"])
    fig = base.nova_figura(ctx.tema, altura=320)
    anos = sorted({str(m)[:4] for m in meses})
    for posicao, texto_ano in enumerate(anos):
        if f"{texto_ano}-01" not in meses:
            continue
        fig.add_vrect(
            x0=pd.Timestamp(f"{texto_ano}-01-01"), x1=pd.Timestamp(f"{texto_ano}-02-28"),
            fillcolor=t.superficie_fraca, opacity=1.0, layer="below", line_width=0,
            annotation_text="IPVA e licenciamento" if posicao == len(anos) - 1 else "",
            annotation_position="top left",
            annotation_font_size=theme.TIPOGRAFIA["nota"],
            annotation_font_color=t.tinta_fraca,
        )
    fig.add_trace(
        go.Bar(
            x=base.datas_de(meses), y=mensal["custo_total"], name="Custo total",
            marker={"color": slot1,
                    "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
            **rotulos_custo,
            customdata=mensal[["custo_fixo", "custo_variavel", "custo_nao_caixa"]].to_numpy(),
            hovertemplate="competência %{x|%b/%Y}: R$ %{y:,.0f}<br>fixo R$ %{customdata[0]:,.0f}"
                          "<br>variável R$ %{customdata[1]:,.0f}"
                          "<br>não caixa R$ %{customdata[2]:,.0f}<extra></extra>",
        )
    )
    base.eixo_mensal(fig, meses)
    fig.update_yaxes(
        showticklabels=not rotulos_custo,
        title_text="R$ no mês", title_font_size=theme.TIPOGRAFIA["nota"],
        tickformat=".2s", rangemode="tozero",
    )
    base.mostrar_grafico(
        fig, chave="p4_mensal",
        nota="Janeiro e fevereiro carregam o IPVA e o licenciamento do ano inteiro: o pico não "
             "é deterioração operacional.",
        dados=mensal,
        colunas_dados=["ano_mes", "custo_total", "custo_alocado", "custo_ocioso", "custo_fixo",
                       "custo_variavel", "custo_nao_caixa", "qtd_veiculos"],
    )

# --------------------------------------------------------------------------
# De que e feito o custo?  |  Fixo, variavel ou nao caixa?
# --------------------------------------------------------------------------
col_cat, col_nat = st.columns([7, 5], gap="medium")

with col_cat:
    ui.cabecalho_secao("De que é feito o custo?")
    categorias = base.obter(dados, "categorias")
    if categorias is None:
        ui.erro_metrica("o custo por categoria", base.falhou(dados, "categorias"))
    else:
        categorias = categorias.sort_values("custo_total", ascending=False)
        cores, textos = [], []
        for nome, participacao in zip(categorias["categoria_custo"],
                                      categorias["participacao_pct"]):
            destaque = nome == CATEGORIA_OCIOSA
            cores.append(t.marca_atencao if destaque else slot1)
            glifo = f" {theme.ICONE_NIVEL['atencao']}" if destaque else ""
            textos.append(f"{fmt.percentual(participacao, 1)}{glifo}")
        fig = base.nova_figura(ctx.tema, altura=400, margin={"l": 220, "r": 80, "t": 16, "b": 48})
        base.barra_horizontal(
            fig, rot.valores(categorias["categoria_custo"]), list(categorias["custo_total"]),
            cores=cores, textos=textos, tema=ctx.tema,
            hover=[f"{rot.valor(c)}<br>{fmt.moeda(v)}<br>{fmt.percentual(p, 1)} do custo"
                   for c, v, p in zip(categorias["categoria_custo"], categorias["custo_total"],
                                      categorias["participacao_pct"])],
        )
        fig.update_xaxes(
            title_text="R$ no período", title_font_size=theme.TIPOGRAFIA["nota"], tickformat=".2s",
        )
        base.mostrar_grafico(
            fig, chave="p4_categorias",
            nota="Pátio e ociosidade vem destacada: é a única categoria que não tem contrato "
                 "nenhum por trás.",
            dados=categorias,
            colunas_dados=["categoria_custo", "custo_total", "custo_fixo", "custo_variavel",
                           "custo_nao_caixa", "participacao_pct"],
        )

with col_nat:
    ui.cabecalho_secao("Fixo, variável ou não caixa?")
    naturezas = base.obter(dados, "naturezas")
    if naturezas is None:
        ui.erro_metrica("o custo por natureza", base.falhou(dados, "naturezas"))
    else:
        ordem = ["Fixo", "Variavel", "Nao Caixa"]
        presentes = [o for o in ordem if o in set(naturezas["tipo_custo"])]
        naturezas = naturezas.set_index("tipo_custo").reindex(presentes).reset_index()
        passos = theme.rampa("neutra", ctx.tema, max(2, len(naturezas)), ordinal=True)
        fig = base.nova_figura(ctx.tema, altura=210, hovermode="closest",
                               margin={"l": 16, "r": 16, "t": 8, "b": 48})
        base.barra_empilhada_100(
            fig,
            [
                (rot.valor(linha["tipo_custo"]), float(linha["participacao_pct"]),
                 float(linha["custo_total"]), passos[min(posicao, len(passos) - 1)])
                for posicao, (_, linha) in enumerate(naturezas.iterrows())
            ],
            tema=ctx.tema,
        )
        fig.update_xaxes(
            title_text="Participação no custo do período", title_font_size=theme.TIPOGRAFIA["nota"],
            ticksuffix="%", range=[0, 100],
        )
        base.mostrar_grafico(
            fig, chave="p4_naturezas",
            nota="A parcela não caixa é depreciação: ela pesa no resultado, mas não sai do caixa.",
            dados=naturezas,
            colunas_dados=["tipo_custo", "custo_total", "participacao_pct"],
        )

# --------------------------------------------------------------------------
# Quanto custa a frota parada?
# --------------------------------------------------------------------------
ui.cabecalho_secao("Quanto custa a frota parada?", ancora="ociosidade")
if sem_ociosidade:
    ui.bloco_desabilitado(
        "Veículo parado não tem cliente, segmento nem contrato. Com o recorte ativo este bloco "
        "ficaria zerado em vez de filtrado, então ele fica desabilitado.",
        acao="Use 'limpar filtros' na barra lateral para vê-lo.",
    )
else:
    ocio = base.obter(dados, "ociosidade")
    if ocio is None:
        ui.erro_metrica("a série de ociosidade", base.falhou(dados, "ociosidade"))
    else:
        meses = list(ocio["ano_mes"])
        eixo_x = base.datas_de(meses)
        ambar_a15, vermelho_a15 = base.limiares_de(df_alertas, "A15")
        niveis = [base.nivel_do_valor(df_alertas, "A15", v) for v in ocio["taxa_ociosidade_pct"]]
        cores_ponto = [theme.cor_nivel(n, ctx.tema) if n != "neutro" else slot1 for n in niveis]
        # Dois graficos lado a lado, nao um dividido em dois paineis. Sao duas
        # perguntas distintas -- quanto da frota esta parada e quanto isso custa --
        # e cada uma tem sua unidade e sua escala. Empilhados, o eixo x compartilhado
        # sugeria uma leitura vertical mes a mes que nenhuma das duas pede, e o
        # painel de baixo ficava com metade da altura util.
        col_taxa, col_custo = st.columns([6, 6], gap="medium")

        # Titulo no proprio grafico, alinhado a esquerda e no tamanho de rotulo --
        # o mesmo padrao dos cinco graficos da pagina de metas.
        titulo_lado = {"x": 0, "xanchor": "left", "y": 0.97, "yanchor": "top",
                       "font": {"size": theme.TIPOGRAFIA["rotulo"]}}

        with col_taxa:
            fig = base.nova_figura(ctx.tema, altura=320)
            teto_taxa = base.maximo_da_coluna(ocio, "taxa_ociosidade_pct", 1.0)
            for limiar, nivel in ((ambar_a15, "atencao"), (vermelho_a15, "critico")):
                if limiar is not None:
                    fig.add_hrect(
                        y0=limiar, y1=max(teto_taxa * 1.2, limiar * 1.4),
                        fillcolor=theme.cor_nivel(nivel, ctx.tema), opacity=0.08, line_width=0,
                        layer="below",
                    )
            fig.add_trace(
                go.Scatter(
                    x=eixo_x, y=ocio["taxa_ociosidade_pct"], mode="lines+markers",
                    name="Parcela da frota parada",
                    line={"color": slot1, "width": theme.ESPESSURA_LINHA},
                    marker={"size": theme.TAMANHO_MARCADOR + 2, "color": cores_ponto,
                            "line": {"color": t.superficie, "width": 1}},
                    customdata=ocio[["qtd_veiculos_ociosos", "qtd_veiculos_frota"]].to_numpy(),
                    hovertemplate="%{x|%b/%Y}: %{y:.1f}%<br>%{customdata[0]} de %{customdata[1]} "
                                  "veículos parados<extra></extra>",
                ),
            )
            pior = ocio.sort_values("taxa_ociosidade_pct", ascending=False).iloc[0]
            nivel_pior = base.nivel_do_valor(df_alertas, "A15", pior["taxa_ociosidade_pct"])
            if nivel_pior != "neutro":
                fig.add_annotation(
                    x=pd.Timestamp(str(pior["ano_mes"]) + "-01"),
                    y=float(pior["taxa_ociosidade_pct"]),
                    text=(f"{theme.ICONE_NIVEL[nivel_pior]} "
                          f"{fmt.competencia(pior['ano_mes'], longo=True)}: "
                          f"{fmt.percentual(pior['taxa_ociosidade_pct'], 1)}"),
                    showarrow=False, yshift=18, xanchor="center",
                    font={"size": theme.TIPOGRAFIA["nota"],
                          "color": theme.cor_nivel(nivel_pior, ctx.tema, uso="texto")},
                )
            base.eixo_mensal(fig, meses)
            fig.update_yaxes(
                title_text="% da frota do mês", title_font_size=theme.TIPOGRAFIA["nota"],
                ticksuffix="%", rangemode="tozero",
            )
            fig.update_layout(
                showlegend=False, hovermode="x unified",
                title={"text": "Parcela da frota sem contrato", **titulo_lado},
                margin={"t": 46},
            )
            base.mostrar_grafico(
                fig, chave="p4_ociosidade_taxa",
                nota="As faixas horizontais marcam a partir de quanto a ociosidade entra em "
                     "atenção e em alerta.",
                dados=ocio,
                colunas_dados=["ano_mes", "taxa_ociosidade_pct", "qtd_veiculos_ociosos",
                               "qtd_veiculos_frota"],
            )

        with col_custo:
            rotulos_ocio = base.rotulos_de_barra(ocio["custo_ocioso"])
            fig = base.nova_figura(ctx.tema, altura=320)
            fig.add_trace(
                go.Bar(
                    x=eixo_x, y=ocio["custo_ocioso"], name="Custo do veículo parado",
                    marker={"color": slot1, "line": {"color": t.superficie, "width": 1}},
                    **rotulos_ocio,
                    hovertemplate="%{x|%b/%Y}: R$ %{y:,.0f}<extra></extra>",
                ),
            )
            base.eixo_mensal(fig, meses)
            fig.update_yaxes(
                title_text="R$ no mês", title_font_size=theme.TIPOGRAFIA["nota"],
                tickformat=".2s", rangemode="tozero",
                showticklabels=not rotulos_ocio,
            )
            fig.update_layout(
                showlegend=False, hovermode="x unified", bargap=0.3,
                title={"text": "Custo do veículo parado", **titulo_lado},
                margin={"t": 46},
            )
            base.mostrar_grafico(
                fig, chave="p4_ociosidade_custo",
                dados=ocio,
                colunas_dados=["ano_mes", "custo_ocioso", "pct_do_custo_total"],
            )

# --------------------------------------------------------------------------
# Qual categoria de veiculo custa mais?
# --------------------------------------------------------------------------
ui.cabecalho_secao("Qual categoria de veículo custa mais?", ancora="veiculos")
por_veiculo = base.obter(dados, "por_veiculo")
if por_veiculo is not None:
    por_veiculo = por_veiculo.assign(categoria=por_veiculo["categoria"].map(rot.valor))
ui.tabela_com_barra(
    por_veiculo if por_veiculo is not None else pd.DataFrame(),
    colunas={
        "categoria": ui.ColunaSpec("Categoria", "texto"),
        "custo_total": ui.ColunaSpec("Custo total", "brl_compacto"),
        "custo_fixo": ui.ColunaSpec("Custo fixo", "brl_compacto"),
        "custo_variavel": ui.ColunaSpec("Custo variável", "brl_compacto"),
        "custo_nao_caixa": ui.ColunaSpec("Custo não caixa", "brl_compacto"),
        "custo_ocioso": ui.ColunaSpec(
            "Veículo parado", "brl_compacto",
            ajuda="Some as categorias e você tem o pátio inteiro: é a parcela sem contrato.",
        ),
        "participacao_pct": ui.ColunaSpec("Participação", "pct"),
    },
    barra="custo_total",
    rotulo_barra="Peso",
    escala="neutra",
    ordenar_por="custo_total",
    limite=None,
    chave="p4_categorias_veiculo",
    tema=ctx.tema,
    vazio_corpo="Nenhum custo de veículo no recorte selecionado.",
)

base.barra_qualidade(df_alertas, tema=ctx.tema)
