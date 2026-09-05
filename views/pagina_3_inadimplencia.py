"""Pagina 3 -- Inadimplencia. "Quanto esta em aberto hoje, e com quem?"

**So a posicao atual.** A serie historica de inadimplencia saiu do projeto: aqui
tudo e a leitura da carteira numa data, e o seletor de data sobe para
o cabecalho porque nesta pagina ele e o controle principal, nao um ajuste.

O caminho empresa -> segmento -> cliente -> **fatura** tem que ser percorrivel
sem sair da pagina.

Deliberadamente fora: qualquer linha do tempo de inadimplencia, recuperacao por
safra, atraso medio ponderado e comparacao com meta por segmento ou rating
(essas metas so existem no nivel Empresa).
"""

from __future__ import annotations


import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frotas import config
from frotas.metrics import credito
from frotas.ui import componentes as ui
from frotas.ui import format as fmt
from frotas.ui import rotulos as rot
from frotas.ui import theme
from views import _comum as base

PAGINA = 3

# O seletor de data vive na barra lateral, junto dos demais filtros: e um filtro
# como outro qualquer, e ter um controle solto no topo da pagina quebrava a regra
# de "todo filtro fica no mesmo lugar".
ctx = base.contexto()
base.abrir_pagina(ctx, "Quanto está em aberto hoje, e com quem?",
                  secao="Inadimplência", pagina=PAGINA)
t = theme.tokens(ctx.tema)
f, ref = ctx.filtros, ctx.data_ref

with st.spinner("Fotografando a carteira..."):
    dados = base.carregar(
        {
            "alertas": lambda: base.avaliar_alertas(f, ref, base.ALERTAS_DA_PAGINA[PAGINA]),
            "inadimplencia": lambda: credito.inadimplencia_ponto_no_tempo(f, ref),
            "aging": lambda: credito.aging_carteira(f, ref),
            "aging_cliente": lambda: credito.aging_por_cliente(f, ref),
            "risco_segmento": lambda: credito.risco_por_segmento(f, ref),
            "risco_rating": lambda: credito.risco_por_rating(f, ref),
            "risco_cliente": lambda: credito.risco_por_cliente(f, ref, limite=None),
        }
    )

df_alertas = base.obter(dados, "alertas")
pit = base.obter(dados, "inadimplencia")
aging = base.obter(dados, "aging")


# --------------------------------------------------------------------------
# Faixa de KPIs -- tudo e a leitura em ref
# --------------------------------------------------------------------------
carteira = base.soma(aging, "valor_bruto")
vencido = None
acima_180 = None
if aging is not None:
    vencidas = aging[aging["faixa"] != "A vencer"]
    vencido = float(vencidas["valor_bruto"].sum()) if not vencidas.empty else 0.0
    faixa_180 = aging[aging["faixa"] == "180+d"]
    acima_180 = float(faixa_180["valor_bruto"].sum()) if not faixa_180.empty else 0.0

janela = ""
if pit is not None:
    ini, fim = base.texto_celula(pit, "janela_ini"), base.texto_celula(pit, "janela_fim")
    if ini and fim:
        janela = fmt.periodo(ini, fim)
janela_incompleta = pit is not None and not bool(pit.iloc[0].get("janela_completa", True))
# Sem badge de data nos tiles: nesta pagina *todos* os numeros sao a leitura da
# data escolhida, e o cabecalho ja a declara.

base.faixa_kpis(
    [
        {
            "rotulo": "Inadimplência acima de 30 dias",
            "valor": base.celula(pit, "inadimplencia_pct"),
            "unidade": "pct", "casas": 2, "chave_direcao": "inadimplencia_30d",
            "estado": "sem_meta",
            "nota": f"sobre o faturamento de {janela}" if janela else None,
            "badges": ["janela de 12m incompleta"] if janela_incompleta else [],
            "ajuda": "Vencido há mais de 30 dias e ainda em aberto nessa data, sobre o faturamento "
                     "bruto dos 12 meses de competência que terminam nela.",
        },
        {
            "rotulo": "Vencido há mais de 30 dias",
            "valor": base.celula(pit, "valor_vencido_30d"),
            "unidade": "brl", "chave_direcao": "carteira_vencida", "estado": "sem_meta",
            "nota": f"{fmt.contagem(base.celula(pit, 'qtd_titulos_vencidos'))} faturas",
            "ajuda": "Numerador da inadimplência: não pago e não cancelado nessa data.",
        },
        {
            "rotulo": "Carteira em aberto",
            "valor": carteira, "unidade": "brl", "chave_direcao": "carteira_vencida",
            "estado": "sem_meta" if carteira is not None else "erro",
            "nota": "vencido ou a vencer",
            "ajuda": "Exclui faturas pagas, canceladas e baixadas até essa data.",
        },
        {
            "rotulo": "Já vencido",
            "valor": vencido, "unidade": "brl", "chave_direcao": "carteira_vencida",
            "estado": "sem_meta" if vencido is not None else "erro",
            "nota": (f"{fmt.percentual(vencido / carteira * 100, 1)} da carteira"
                     if carteira else None),
            "ajuda": "Soma de todas as faixas de atraso, do primeiro dia em diante.",
        },
        {
            "rotulo": "Vencido há mais de 180 dias",
            "valor": acima_180, "unidade": "brl", "chave_direcao": "carteira_vencida",
            "estado": "sem_meta" if acima_180 is not None else "erro",
            "nota": "vira baixa aos 365 dias",
            "ajuda": "A faixa mais antiga da carteira: é dela que sai a perda provável.",
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

ui.nota_armadilha(
    f"Tudo nesta página mostra como a carteira estava em {fmt.data_br(ref)}. "
    "porque uma fatura de 2024 ainda vencida conta na posição de hoje. A carteira exclui faturas "
    "baixadas; a inadimplência não. As duas leituras estão certas e diferem em R$ 328 mil."
)

# --------------------------------------------------------------------------
# Qual a idade do que esta em aberto?
# --------------------------------------------------------------------------
ui.cabecalho_secao("Qual a idade do que está em aberto?", ancora="aging")
faixa_escolhida = None
if aging is None:
    ui.erro_metrica("as faixas de atraso da carteira", base.falhou(dados, "aging"))
else:
    vencidas = aging[aging["faixa"] != "A vencer"]
    cores_risco = theme.rampa("risco", ctx.tema, max(2, len(vencidas)), ordinal=True)
    fig = base.nova_figura(ctx.tema, altura=180, hovermode="closest",
                           margin={"l": 16, "r": 16, "t": 8, "b": 48})
    indice_risco = 0
    for _, linha in aging.iterrows():
        eh_a_vencer = linha["faixa"] == "A vencer"
        cor = t.marca_neutro if eh_a_vencer else cores_risco[min(indice_risco, len(cores_risco) - 1)]
        if not eh_a_vencer:
            indice_risco += 1
        participacao = float(linha["participacao_pct"])
        nome = rot.faixa_aging(linha["faixa"])
        fig.add_trace(
            go.Bar(
                x=[float(linha["valor_bruto"])], y=["Carteira"], orientation="h", name=nome,
                marker={"color": cor,
                        "line": {"color": t.superficie, "width": theme.FOLGA_ENTRE_MARCAS}},
                text=(f"{nome}<br>{fmt.moeda_compacta(linha['valor_bruto'])}"
                      f" ({fmt.percentual(participacao, 1)})") if participacao >= 5 else "",
                textposition="inside", insidetextanchor="middle",
                textfont={"size": theme.TIPOGRAFIA["nota"], "color": t.superficie},
                hovertemplate=(f"{nome}<br>{fmt.moeda(linha['valor_bruto'])}<br>"
                               f"{fmt.contagem(linha['qtd_titulos'])} faturas<br>"
                               f"{fmt.percentual(participacao, 1)} da carteira<extra></extra>"),
            )
        )
    fig.update_layout(barmode="stack", showlegend=False)
    fig.update_yaxes(showticklabels=False, showgrid=False)
    fig.update_xaxes(
        title_text="R$ em aberto na data escolhida (da esquerda para a direita: a vencer até "
                   "mais de 180 dias)",
        title_font_size=theme.TIPOGRAFIA["nota"], tickformat=".2s",
    )
    base.mostrar_grafico(fig, chave="p3_aging", dados=aging)
    faixa_escolhida = st.segmented_control(
        "Recortar a fila de cobrança por faixa de atraso",
        options=list(aging["faixa"]),
        format_func=rot.faixa_aging,
        selection_mode="single",
        key="faixa_aging",
        help="Equivale a clicar na faixa da barra: recorta a tabela de clientes mais abaixo.",
    )

# --------------------------------------------------------------------------
# Quais segmentos?  |  Quais ratings?
# --------------------------------------------------------------------------
col_seg, col_rat = st.columns([7, 5], gap="medium")

with col_seg:
    ui.cabecalho_secao("Quais segmentos concentram o atraso?")
    risco_seg = base.obter(dados, "risco_segmento")
    if risco_seg is None:
        ui.erro_metrica("o risco por segmento", base.falhou(dados, "risco_segmento"))
    else:
        risco_seg = risco_seg.copy()
        risco_seg["inadimplencia_pct"] = pd.to_numeric(
            risco_seg["inadimplencia_pct"], errors="coerce"
        )
        risco_seg = risco_seg.sort_values("inadimplencia_pct", ascending=False)
        empresa = base.celula(pit, "inadimplencia_pct")
        ambar_a9, vermelho_a9 = base.limiares_de(df_alertas, "A9")
        niveis = []
        for valor in risco_seg["inadimplencia_pct"]:
            razao = None if (empresa in (None, 0) or fmt.eh_vazio(valor)) else float(valor) / empresa
            niveis.append(base.nivel_do_valor(df_alertas, "A9", razao))
        cores = [
            theme.cor_nivel(n, ctx.tema) if n != "neutro" else theme.cor_segmento(s, ctx.tema)
            for n, s in zip(niveis, risco_seg["segmento"])
        ]
        fig = base.nova_figura(ctx.tema, altura=340, margin={"l": 180, "r": 90, "t": 16, "b": 48})
        base.barra_horizontal(
            fig,
            rot.valores(risco_seg["segmento"]),
            [0.0 if fmt.eh_vazio(v) else float(v) for v in risco_seg["inadimplencia_pct"]],
            cores=cores,
            textos=[fmt.percentual(v, 1) for v in risco_seg["inadimplencia_pct"]],
            tema=ctx.tema,
            hover=[f"{rot.valor(s)}<br>inadimplência {fmt.percentual(i, 2)}<br>"
                   f"vencido {fmt.moeda_compacta(v)}<br>carteira {fmt.moeda_compacta(c)}"
                   for s, i, v, c in zip(risco_seg["segmento"], risco_seg["inadimplencia_pct"],
                                         risco_seg["vencido_30d_mais"], risco_seg["carteira_total"])],
        )
        if empresa:
            for limiar, nivel in ((ambar_a9, "atencao"), (vermelho_a9, "critico")):
                if limiar is not None:
                    fig.add_vline(
                        x=empresa * limiar, line_width=1, line_dash="dash", line_color=t.eixo,
                        annotation_text=f"{theme.ICONE_NIVEL[nivel]} {fmt.vezes(limiar)} a empresa",
                        annotation_position="top", annotation_font_size=theme.TIPOGRAFIA["nota"],
                        annotation_font_color=t.tinta_fraca,
                    )
        fig.update_xaxes(
            title_text="Vencido há mais de 30 dias sobre o faturamento de 12 meses do segmento",
            title_font_size=theme.TIPOGRAFIA["nota"], ticksuffix="%",
        )
        base.mostrar_grafico(
            fig, chave="p3_segmentos",
            nota="Cada barra usa o denominador do próprio segmento: a média das barras não é a "
                 "inadimplência da empresa.",
            dados=risco_seg,
        )

with col_rat:
    ui.cabecalho_secao("De qual rating vem o vencido?")
    rating = base.obter(dados, "risco_rating")
    if rating is None:
        ui.erro_metrica("a exposição por rating", base.falhou(dados, "risco_rating"))
    else:
        rating = rating.sort_values("rating_credito")
        total_venc = float(pd.to_numeric(rating["vencido_30d_mais"], errors="coerce").sum()) or 1.0
        passos = theme.rampa("neutra", ctx.tema, max(2, len(rating)), ordinal=True)
        fig = base.nova_figura(ctx.tema, altura=210, hovermode="closest",
                               margin={"l": 16, "r": 16, "t": 8, "b": 48})
        base.barra_empilhada_100(
            fig,
            [
                (f"Rating {linha['rating_credito']}",
                 float(linha["vencido_30d_mais"]) / total_venc * 100,
                 float(linha["vencido_30d_mais"]),
                 passos[min(posicao, len(passos) - 1)])
                for posicao, (_, linha) in enumerate(rating.iterrows())
            ],
            tema=ctx.tema,
        )
        fig.update_xaxes(
            title_text="Participação no vencido há mais de 30 dias, do rating A ao D",
            title_font_size=theme.TIPOGRAFIA["nota"], ticksuffix="%", range=[0, 100],
        )
        base.mostrar_grafico(
            fig, chave="p3_ratings",
            nota="Rating é atributo estático do cadastro: ele não é revisto quando o cliente "
                 "começa a atrasar.",
            dados=rating,
        )

# --------------------------------------------------------------------------
# Quem, exatamente?
# --------------------------------------------------------------------------
ui.cabecalho_secao("Quem, exatamente?", ancora="clientes")
risco_cli = base.obter(dados, "risco_cliente")
if risco_cli is None:
    ui.erro_metrica("o risco por cliente", base.falhou(dados, "risco_cliente"))
else:
    risco_cli = risco_cli.copy()
    for coluna in ("pct_vencido_30d", "inadimplencia_pct", "uso_limite_pct"):
        risco_cli[coluna] = pd.to_numeric(risco_cli[coluna], errors="coerce")
    risco_cli = risco_cli[pd.to_numeric(risco_cli["faturamento_bruto_12m"], errors="coerce") > 0]
    ambar_a7, vermelho_a7 = base.limiares_de(df_alertas, "A7")
    ordem_rating = ["A", "B", "C", "D"]
    # Rating e escala de risco: A verde, B neutro, C ambar, D vermelho.
    cor_por_rating = {n: theme.cor_rating(n, ctx.tema) for n in ordem_rating}

    fig = base.nova_figura(ctx.tema, altura=360, hovermode="closest")
    maior_venc = base.maximo_da_coluna(risco_cli, "vencido_30d_mais", 1.0) or 1.0
    for nota_rating in ordem_rating:
        grupo = risco_cli[risco_cli["rating_credito"] == nota_rating]
        if grupo.empty:
            continue
        contornos = [
            t.marca_critico
            if (vermelho_a7 is not None and not fmt.eh_vazio(v) and float(v) >= vermelho_a7)
            else t.superficie
            for v in grupo["pct_vencido_30d"]
        ]
        fig.add_trace(
            go.Scatter(
                x=grupo["faturamento_bruto_12m"], y=grupo["pct_vencido_30d"], mode="markers",
                name=f"Rating {nota_rating}",
                marker={
                    "size": (grupo["vencido_30d_mais"] / maior_venc * 40 + 8).tolist(),
                    "color": cor_por_rating[nota_rating],
                    "line": {"color": contornos, "width": 2},
                },
                customdata=grupo[["nome_cliente", "vencido_30d_mais", "uso_limite_pct",
                                  "segmento"]].to_numpy(),
                hovertemplate=(
                    "%{customdata[0]}<br>%{customdata[3]} · rating " + nota_rating
                    + "<br>faturado em 12 meses: R$ %{x:,.0f}"
                      "<br>vencido há mais de 30 dias: R$ %{customdata[1]:,.0f} (%{y:.1f}%)"
                      "<br>uso do limite: %{customdata[2]:.0f}%<extra></extra>"
                ),
            )
        )
    for limiar, nivel in ((ambar_a7, "atencao"), (vermelho_a7, "critico")):
        if limiar is not None:
            fig.add_hline(
                y=limiar, line_width=1, line_dash="dash", line_color=t.eixo,
                annotation_text=f"{theme.ICONE_NIVEL[nivel]} {fmt.percentual(limiar, 0)} "
                                "do próprio faturamento",
                annotation_position="top left",
                annotation_font_size=theme.TIPOGRAFIA["nota"],
                annotation_font_color=t.tinta_fraca,
            )
    minimo_fat = float(pd.to_numeric(risco_cli["faturamento_bruto_12m"], errors="coerce").min() or 1)
    razao = base.maximo_da_coluna(risco_cli, "faturamento_bruto_12m", 1.0) / max(minimo_fat, 1.0)
    fig.update_xaxes(
        title_text="R$ faturado ao cliente nos últimos 12 meses",
        title_font_size=theme.TIPOGRAFIA["nota"], tickformat=".2s",
        type="log" if razao > 100 else "linear",
    )
    fig.update_yaxes(
        title_text="Parcela do próprio faturamento de 12 meses vencida há mais de 30 dias",
        title_font_size=theme.TIPOGRAFIA["nota"], ticksuffix="%", rangemode="tozero",
    )
    fig.update_layout(showlegend=True, legend={"orientation": "h", "y": 1.12, "x": 0})
    base.mostrar_grafico(
        fig, chave="p3_clientes",
        nota="Tamanho da bolha é o valor vencido; anel vermelho marca quem passou do limiar "
             "crítico da regra de crédito.",
        dados=risco_cli,
    )

# --------------------------------------------------------------------------
# A fila de cobranca, com drill ate a fatura
# --------------------------------------------------------------------------
ui.cabecalho_secao("Por onde começar a cobrança?", ancora="fila")
aging_cli = base.obter(dados, "aging_cliente")
if aging_cli is None:
    ui.erro_metrica("a fila de cobrança", base.falhou(dados, "aging_cliente"))
else:
    fila = aging_cli.copy()
    for coluna in ("pct_vencido_30d", "uso_limite_pct"):
        fila[coluna] = pd.to_numeric(fila[coluna], errors="coerce")
    if faixa_escolhida and faixa_escolhida in fila.columns:
        fila = fila[pd.to_numeric(fila[faixa_escolhida], errors="coerce").fillna(0) > 0]
    ambar_a8, vermelho_a8 = base.limiares_de(df_alertas, "A8")

    def _uso_limite(valor: float | None) -> str:
        """Uso do limite com o glifo do nivel -- o corte vem da regra A8."""
        if fmt.eh_vazio(valor):
            return fmt.VAZIO
        texto = fmt.percentual(valor, 0)
        if vermelho_a8 is not None and float(valor) >= vermelho_a8:
            return f"{theme.ICONE_NIVEL['critico']} {texto}"
        if ambar_a8 is not None and float(valor) >= ambar_a8:
            return f"{theme.ICONE_NIVEL['atencao']} {texto}"
        return texto

    fila["uso_limite_txt"] = fila["uso_limite_pct"].map(_uso_limite)
    fila["segmento"] = fila["segmento"].map(rot.valor)
    fila["porte"] = fila["porte"].map(rot.valor)
    fila = fila.sort_values("vencido_30d_mais", ascending=False).head(20).reset_index(drop=True)
    selecao = ui.tabela_com_barra(
        fila,
        colunas={
            "nome_cliente": ui.ColunaSpec("Cliente", "texto", largura="large"),
            "segmento": ui.ColunaSpec("Segmento", "texto", largura="medium"),
            "rating_credito": ui.ColunaSpec("Rating", "texto", largura="small"),
            "carteira_total": ui.ColunaSpec(
                "Em aberto", "brl_compacto",
                ajuda="Tudo que ainda não foi pago, vencido ou a vencer.",
            ),
            "vencido_30d_mais": ui.ColunaSpec(
                "Vencido", "brl_compacto",
                ajuda="Valor vencido há mais de 30 dias e ainda não pago nessa data.",
            ),
            "pct_vencido_30d": ui.ColunaSpec(
                "% da receita", "pct",
                ajuda="Quanto o vencido representa do que esse cliente faturou nos "
                      "últimos 12 meses.",
            ),
            "uso_limite_txt": ui.ColunaSpec(
                "Uso do limite", "texto",
                ajuda="O glifo segue o limiar publicado da regra de crédito, não um corte da tela.",
            ),
        },
        barra="vencido_30d_mais",
        rotulo_barra="Peso",
        escala="risco",
        ordenar_por=None,
        limite=None,
        chave="p3_fila",
        selecionavel=True,
        tema=ctx.tema,
        vazio_titulo="Nenhum cliente nesta faixa de atraso",
        vazio_corpo="Nenhum cliente do recorte tem saldo nesta faixa na data escolhida.",
    )
    st.caption("Clique numa linha para abrir as faturas do cliente.")

    linhas_sel = []
    if selecao is not None and hasattr(selecao, "selection"):
        linhas_sel = list(getattr(selecao.selection, "rows", []) or [])
    if linhas_sel and linhas_sel[0] < len(fila):
        cliente = fila.iloc[linhas_sel[0]]
        with st.expander(f"Faturas de {cliente['nome_cliente']}", expanded=True):
            col_a, col_b = st.columns([4, 8], gap="medium")
            with col_a:
                faixas = [c for c in config.FAIXAS_AGING if c in fila.columns]
                # fmt.sem_latex em todo valor em reais: dois "R$" na mesma string
                # fariam o Markdown do Streamlit abrir LaTeX e engolir o texto.
                st.markdown(
                    f"**Carteira em aberto** {fmt.sem_latex(fmt.moeda(cliente['carteira_total']))}  \n"
                    f"**Vencido há mais de 30 dias** "
                    f"{fmt.sem_latex(fmt.moeda(cliente['vencido_30d_mais']))}  \n"
                    f"**Uso do limite de crédito** {cliente['uso_limite_txt']}  \n"
                    f"**Rating** {cliente['rating_credito']} · **Porte** {cliente['porte']}"
                )
                st.dataframe(
                    pd.DataFrame(
                        {
                            "Faixa de atraso": [rot.faixa_aging(c) for c in faixas],
                            "Em aberto": [fmt.moeda_compacta(cliente[c]) for c in faixas],
                        }
                    ),
                    hide_index=True, width="stretch",
                )
            with col_b:
                try:
                    faturas = credito.titulos_do_cliente(f, str(cliente["id_cliente"]), ref)
                except Exception as exc:  # noqa: BLE001 - erro do drill nao derruba a pagina
                    faturas = None
                    ui.erro_metrica("as faturas do cliente", f"{type(exc).__name__}: {exc}")
                if faturas is not None and not faturas.empty:
                    abertas = faturas[faturas["status_calculado"] != "Pago"]
                    visao = (abertas if not abertas.empty else faturas).copy()
                    visao = visao.sort_values("data_vencimento", ascending=False).head(40)
                    visao["faixa"] = visao["faixa"].map(rot.faixa_aging)
                    visao["status_calculado"] = visao["status_calculado"].map(rot.valor)
                    ui.tabela_com_barra(
                        visao,
                        colunas={
                            "id_titulo": ui.ColunaSpec("Fatura", "texto", largura="small"),
                            "competencia": ui.ColunaSpec("Competência", "competencia"),
                            "data_vencimento": ui.ColunaSpec("Vencimento", "data"),
                            "dias_atraso": ui.ColunaSpec("Dias", "dias", ajuda="Dias de atraso na data escolhida."),
                            "faixa": ui.ColunaSpec("Atraso", "texto", largura="small"),
                            "valor_bruto": ui.ColunaSpec("Valor", "brl"),
                            "status_calculado": ui.ColunaSpec(
                                "Situação", "texto",
                                ajuda="Como a fatura estava na data escolhida.",
                            ),
                        },
                        barra="valor_bruto",
                        rotulo_barra="Valor",
                        escala="risco",
                        ordenar_por=None,
                        limite=None,
                        chave="p3_faturas_cliente",
                        tema=ctx.tema,
                        vazio_titulo=f"Nada em aberto para este cliente em {fmt.data_br(ref)}",
                    )
                    st.caption(
                        "A situação é recalculada na data escolhida, nunca lida da situação gravada "
                        "na extração."
                    )

base.barra_qualidade(df_alertas, tema=ctx.tema)
