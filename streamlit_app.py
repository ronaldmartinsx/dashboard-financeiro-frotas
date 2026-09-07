"""Entrypoint do data app de frotas -- navegacao, tema e filtros globais.

Estrutura::

    streamlit_app.py     nav + sidebar + estado compartilhado (este arquivo)
    views/               uma pagina por arquivo
    frotas/metrics/      camada semantica (unica fonte de dado)
    frotas/ui/           tema, formatacao e componentes

O estado compartilhado e um unico :class:`frotas.filtros.Filtros` em
``st.session_state['filtros']``. Ele e ``frozen`` -- e portanto hashavel -- de
proposito: e ele que entra na chave de ``st.cache_data`` das metricas, entao a
barra lateral **monta um novo objeto** a cada mudanca em vez de mutar o antigo.

A barra lateral chama ``dimensoes.opcoes_filtros()`` **uma vez** no boot: sao 15
dominios em 1 round-trip (~3,8 s a frio, ~2 ms depois). Quinze ``listar_*`` em
serie custariam 14 s.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

_RAIZ = Path(__file__).resolve().parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from frotas import config, db  # noqa: E402
from frotas.filtros import Filtros  # noqa: E402
from frotas.metrics import dimensoes  # noqa: E402
from frotas.ui import componentes as ui  # noqa: E402
from frotas.ui import format as fmt  # noqa: E402
from frotas.ui import rotulos as rot  # noqa: E402
from views import _comum as base  # noqa: E402

#: Nome do produto. Vem de ``ui.NOME_APP`` para que a aba do navegador, o
#: cabecalho de cada pagina e a tela sem banco nunca divirjam.
TITULO = ui.NOME_APP

#: Presets do periodo de competencia (docs/01_kpis.md 7). O padrao sao os 12
#: meses moveis fechados: e a janela em que a inadimplencia e comparavel.
PRESETS_PERIODO: dict[str, tuple[date, date]] = {
    "Últimos 12 meses": (date(2025, 9, 1), date(2026, 8, 1)),
    "2026 (até agosto)": (date(2026, 1, 1), date(2026, 8, 1)),
    "2025": (date(2025, 1, 1), date(2025, 12, 1)),
    "2024": (date(2024, 1, 1), date(2024, 12, 1)),
    "Todo o período": (config.COMPETENCIA_MIN, config.COMPETENCIA_MAX),
    "Escolher os meses": (date(2025, 9, 1), date(2026, 8, 1)),
}

#: A opcao que abre os campos De/Ate. As demais ja definem o intervalo.
PRESET_LIVRE = "Escolher os meses"

_SEM_RATING = "(sem rating)"



# --------------------------------------------------------------------------
# Boot
# --------------------------------------------------------------------------


st.set_page_config(
    page_title=TITULO,
    page_icon=":material/local_shipping:",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=config.TTL_DIMENSOES, show_spinner=False)
def _opcoes() -> dict[str, list[str]]:
    return dimensoes.opcoes_filtros()


@st.cache_data(ttl=config.TTL_DIMENSOES, show_spinner=False)
def _clientes() -> pd.DataFrame:
    return dimensoes.listar_clientes()




def _meses_disponiveis() -> list[date]:
    """Competencias do dataset, geradas dos limites de ``config`` (sem ida ao banco)."""
    marcos = pd.date_range(config.COMPETENCIA_MIN, config.COMPETENCIA_MAX, freq="MS")
    return [d.date() for d in marcos]


def tela_sem_dados(mensagem: str) -> None:
    """Tela util quando o snapshot de dados nao esta la (secao 6.8 do UX).

    Nunca despeja stack trace: o publico desta tela e o CFO. Como o app le
    arquivos do proprio projeto, o conserto e uma linha de comando, e nao a
    configuracao de uma credencial.
    """
    ui.estilos(ui.tema_atual())
    st.title(TITULO)
    st.error(mensagem)
    st.markdown(
        "**Como restaurar os dados**\n\n"
        "1. Os dados do projeto ficam em `dados/`, um arquivo por tabela.\n"
        "2. Se a pasta sumiu, gere de novo com `python3 scripts/exportar_dados.py` "
        "(esse script, e so ele, precisa da credencial do Supabase).\n"
        "3. Recarregue a pagina."
    )
    st.caption("Nenhum numero desta tela foi recalculado.")
    if st.button("tentar de novo"):
        db.limpar_cache()
        st.rerun()


# --------------------------------------------------------------------------
# Barra lateral
# --------------------------------------------------------------------------


def _aplicar_preset() -> None:
    escolha = st.session_state.get("preset_periodo", "Últimos 12 meses")
    if escolha == PRESET_LIVRE:
        return
    ini, fim = PRESETS_PERIODO[escolha]
    st.session_state["comp_ini"] = ini
    st.session_state["comp_fim"] = fim


def barra_lateral(opcoes: dict[str, list[str]], clientes: pd.DataFrame, *, pagina: str) -> Filtros:
    """Monta os filtros globais e devolve o :class:`Filtros` da sessao.

    Ordem: periodo · data da foto · segmento · porte · rating · tipo de contrato ·
    cliente. So filtros: explicacao de metodo mora no Guia, nao aqui.

    Nenhum rotulo de filtro expoe nome de coluna: os valores de dominio passam
    por ``frotas.ui.rotulos`` (o banco guarda "Construcao Civil", a tela mostra
    "Construção Civil").
    """
    meses = _meses_disponiveis()
    if "comp_ini" not in st.session_state:
        st.session_state["comp_ini"], st.session_state["comp_fim"] = PRESETS_PERIODO["Últimos 12 meses"]

    # "" porque o Streamlit serve a pagina default na raiz, com url_path vazio.
    if pagina in ("guia", ""):
        # O Guia nao consulta o banco: mostrar filtros ali e prometer um efeito que
        # nao existe. Os valores escolhidos sobrevivem no session_state e voltam a
        # aparecer -- e a valer -- assim que o usuario entra numa pagina de dados.
        return _filtros_do_estado(clientes)

    exibidos = base.FILTROS_DA_PAGINA.get(base.PAGINA_POR_URL.get(pagina, -1), ())
    est = st.session_state
    comp_ini, comp_fim = est.get("comp_ini"), est.get("comp_fim")
    data_ref = est.get("ref_data", config.DATA_EXTRACAO)
    segmentos = est.get("f_segmentos", [])
    portes = est.get("f_portes", [])
    ratings = est.get("f_ratings", [])
    tipos_contrato = est.get("f_tipos_contrato", [])
    escolhidos = est.get("f_clientes", [])
    nomes = dict(zip(clientes["nome_cliente"], clientes["id_cliente"])) if not clientes.empty else {}

    with st.sidebar:
        st.markdown("### Filtros")

        # Dois grupos com nome: "Quando" (periodo e data) e "Recortes" (as
        # dimensoes). Sem eles a barra abria com "Filtros" e logo em seguida um
        # seletor de data, que nao se le como filtro -- os filtros "de verdade"
        # so vinham depois, e a lista parecia comecar no meio.
        if [c for c in ("periodo", "data", "granularidade") if c in exibidos]:
            st.caption("**Quando**")

        if "ano" in exibidos:
            anos = sorted({d.year for d in meses})
            escolhido = st.selectbox(
                "Exercício", options=anos,
                index=anos.index(st.session_state.get("comp_fim", meses[-1]).year)
                if st.session_state.get("comp_fim", meses[-1]).year in anos else len(anos) - 1,
                key="ano_exercicio",
                help="O ano orçado que a página compara: meta, realizado e série mensal.",
            )
            # O resto do app conversa em competencia; o ano vira o intervalo dele.
            do_ano = [d for d in meses if d.year == escolhido]
            comp_ini, comp_fim = do_ano[0], do_ano[-1]

        if "periodo" in exibidos:
            # Um seletor no lugar de seis opcoes empilhadas, e os campos De/Ate
            # so quando o usuario pede: antes eram tres controles sempre visiveis
            # para escolher um periodo que, em 5 dos 6 casos, ja vinha pronto.
            st.selectbox(
                "Período",
                options=list(PRESETS_PERIODO),
                key="preset_periodo",
                on_change=_aplicar_preset,
                help="Recorta o mês dos valores faturados e dos custos.",
            )
            if st.session_state.get("preset_periodo") == PRESET_LIVRE:
                col_ini, col_fim = st.columns(2)
                with col_ini:
                    comp_ini = st.selectbox(
                        "De", options=meses, key="comp_ini",
                        format_func=lambda d: fmt.competencia(d, longo=True),
                    )
                with col_fim:
                    comp_fim = st.selectbox(
                        "Até", options=meses, key="comp_fim",
                        format_func=lambda d: fmt.competencia(d, longo=True),
                    )
                if comp_ini > comp_fim:
                    st.warning("O mês inicial é posterior ao final; o intervalo foi invertido.")
                    comp_ini, comp_fim = comp_fim, comp_ini

        if "granularidade" in exibidos:
            # Em Metas o exercicio ja e um ano: agrupar por ano deixaria cada
            # grafico com uma barra so, que e a leitura que a matriz de conferencia
            # acima ja da. Sobram mes e trimestre.
            graos = [g for g in base.GRAOS
                     if not (g == "Ano" and "ano" in exibidos)]
            st.selectbox(
                "Agrupar o tempo por",
                options=graos,
                key="granularidade",
                help="Muda o eixo dos gráficos de série. Semana não entra: faturamento, "
                     "custo e meta nascem mensais no sistema de origem.",
            )

        if "data" in exibidos:
            data_ref = ui.seletor_data_referencia(
                valor=data_ref,
                minimo=date(2024, 12, 31),
                maximo=config.DATA_EXTRACAO,
                chave="ref",
                rotulo="Ver como estava em",
            )

        recortes = [c for c in ("segmento", "porte", "rating", "tipo_contrato", "cliente")
                    if c in exibidos]
        if recortes:
            st.divider()
            st.caption("**Recortes**")
        if "segmento" in exibidos:
            segmentos = st.multiselect(
                "Segmento", options=opcoes.get("segmentos", []), key="f_segmentos",
                format_func=rot.valor,
            )
        if "porte" in exibidos:
            portes = st.multiselect(
                "Porte", options=opcoes.get("portes", []), key="f_portes", format_func=rot.valor,
            )
        if "rating" in exibidos:
            ratings = st.multiselect(
                "Rating de crédito", options=list(opcoes.get("ratings", [])) + [_SEM_RATING],
                key="f_ratings",
            )
        if "tipo_contrato" in exibidos:
            tipos_contrato = st.multiselect(
                "Tipo de contrato", options=opcoes.get("tipos_contrato", []),
                key="f_tipos_contrato", format_func=rot.valor,
            )
        if "cliente" in exibidos:
            escolhidos = st.multiselect(
                "Cliente", options=sorted(nomes), placeholder="busque pelo nome",
                key="f_clientes",
            )

        st.divider()
        if st.button("Limpar filtros", icon=":material/filter_alt_off:", width="stretch"):
            for chave in (
                "preset_periodo", "comp_ini", "comp_fim", "ano_exercicio", "granularidade",
                "f_segmentos", "f_portes",
                "f_ratings", "f_tipos_contrato", "f_clientes", "faixa_aging",
                "meta_segmento_indicador",
            ):
                st.session_state.pop(chave, None)
            st.rerun()

    filtros = Filtros.criar(
        competencia_ini=comp_ini,
        competencia_fim=comp_fim,
        data_ref=data_ref,
        segmentos=segmentos,
        portes=portes,
        ratings=[r for r in ratings if r != _SEM_RATING],
        tipos_contrato=tipos_contrato,
        clientes=[nomes[n] for n in escolhidos if n in nomes],
    )
    st.session_state["filtros"] = filtros
    return filtros


def _filtros_do_estado(clientes: pd.DataFrame) -> Filtros:
    """Monta o :class:`Filtros` a partir do ``session_state``, sem desenhar widget.

    Usado nas paginas que nao consomem dado (o Guia): preserva a escolha do
    usuario sem exibir controles que ali nao teriam efeito.
    """
    nomes = dict(zip(clientes["nome_cliente"], clientes["id_cliente"])) if not clientes.empty else {}
    escolhidos = st.session_state.get("f_clientes", [])
    filtros = Filtros.criar(
        competencia_ini=st.session_state.get("comp_ini"),
        competencia_fim=st.session_state.get("comp_fim"),
        data_ref=st.session_state.get("ref_data", config.DATA_EXTRACAO),
        segmentos=st.session_state.get("f_segmentos", []),
        portes=st.session_state.get("f_portes", []),
        ratings=[r for r in st.session_state.get("f_ratings", []) if r != _SEM_RATING],
        tipos_contrato=st.session_state.get("f_tipos_contrato", []),
        clientes=[nomes[n] for n in escolhidos if n in nomes],
    )
    st.session_state["filtros"] = filtros
    return filtros




# --------------------------------------------------------------------------
# Navegacao
# --------------------------------------------------------------------------


#: Uma pergunta por pagina, declarada no titulo. O Guia e a pagina inicial:
#: quem abre o relatorio pela primeira vez comeca sabendo o que vai encontrar.
# O menu leva o nome curto (e um dashboard, nao um sumario); a pergunta de negocio
# continua sendo o titulo dentro da pagina. O icone vem de ``ui.ICONE_SECAO``, o
# mesmo que o cabecalho da pagina usa -- menu e topo nunca divergem.
PAGINAS = [
    st.Page("views/pagina_0_guia.py", title="Guia",
            icon=ui.ICONE_SECAO["Guia"], url_path="guia", default=True),
    st.Page("views/pagina_1_metas.py", title="Metas",
            icon=ui.ICONE_SECAO["Metas"], url_path="metas"),
    st.Page("views/pagina_2_faturamento_recebimento.py",
            title="Faturamento e Recebimento",
            icon=ui.ICONE_SECAO["Faturamento e Recebimento"],
            url_path="faturamento-recebimento"),
    st.Page("views/pagina_3_inadimplencia.py", title="Inadimplência",
            icon=ui.ICONE_SECAO["Inadimplência"], url_path="inadimplencia"),
    st.Page("views/pagina_4_custos.py", title="Custos",
            icon=ui.ICONE_SECAO["Custos"], url_path="custos"),
]


def main() -> None:
    # Primeira coisa do rerun: o <style> do app e recriado a cada redesenho, entao
    # o guard de estilos() -- que vive em session_state e sobrevive ao rerun --
    # precisa ser zerado aqui. Sem isto a pagina volta sem CSS ao trocar de pagina
    # ou mexer num filtro, e so o F5 (sessao nova) devolve o estilo.
    ui.reiniciar_estilos()

    estado = db.verificar_dados()
    if not estado.ok:
        tela_sem_dados(estado.mensagem)
        st.stop()

    pagina = st.navigation(PAGINAS, position="sidebar")
    try:
        opcoes, clientes = _opcoes(), _clientes()
    except Exception as exc:  # noqa: BLE001 - boot da sidebar
        tela_sem_dados(getattr(exc, "mensagem_usuario", "Nao foi possivel ler os dados do projeto."))
        st.stop()

    barra_lateral(opcoes, clientes, pagina=pagina.url_path)
    pagina.run()
    # Uma chamada so, aqui: o rodape e do app, nao de cada pagina. Nenhuma view
    # precisa lembrar dele, e nao ha como uma esquecer.
    ui.rodape()


main()
