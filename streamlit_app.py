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
from frotas.metrics import dimensoes, metas  # noqa: E402
from frotas.ui import componentes as ui  # noqa: E402
from frotas.ui import format as fmt  # noqa: E402
from frotas.ui import rotulos as rot  # noqa: E402

TITULO = "Frotas · Painel financeiro"

#: Presets do periodo de competencia (docs/01_kpis.md 7). O padrao sao os 12
#: meses moveis fechados: e a janela em que a inadimplencia e comparavel.
PRESETS_PERIODO: dict[str, tuple[date, date]] = {
    "Ultimos 12m": (date(2025, 9, 1), date(2026, 8, 1)),
    "2026 YTD (8m)": (date(2026, 1, 1), date(2026, 8, 1)),
    "2025": (date(2025, 1, 1), date(2025, 12, 1)),
    "2024": (date(2024, 1, 1), date(2024, 12, 1)),
    "Tudo": (config.COMPETENCIA_MIN, config.COMPETENCIA_MAX),
    "Personalizado": (date(2025, 9, 1), date(2026, 8, 1)),
}

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


@st.cache_data(ttl=config.TTL_FATOS, show_spinner=False)
def _versoes(ano: int) -> pd.DataFrame:
    return metas.versoes_orcamento(ano)


def _meses_disponiveis() -> list[date]:
    """Competencias do dataset, geradas dos limites de ``config`` (sem ida ao banco)."""
    marcos = pd.date_range(config.COMPETENCIA_MIN, config.COMPETENCIA_MAX, freq="MS")
    return [d.date() for d in marcos]


def tela_sem_banco(mensagem: str) -> None:
    """Tela util quando nao ha credencial ou o banco esta fora (secao 6.8 do UX).

    Nunca cita o valor do segredo -- so a origem e o que fazer. E nunca despeja
    stack trace: o publico desta tela e o CFO.
    """
    ui.estilos(ui.tema_atual())
    st.title(TITULO)
    st.error(mensagem)
    st.markdown(
        "**Como configurar a leitura**\n\n"
        "1. Defina `PG_DSN` em `.streamlit/secrets.toml`, numa variavel de ambiente "
        "ou no `.env` da raiz do projeto.\n"
        "2. A credencial precisa ser de **leitura**: o app nunca escreve no banco.\n"
        "3. Recarregue a pagina depois de configurar."
    )
    diagnostico = [
        {"Segredo": o.nome, "Origem": o.origem or "não encontrado", "Configurado": o.definido}
        for o in config.diagnostico_segredos()
    ]
    st.dataframe(pd.DataFrame(diagnostico), hide_index=True, width="stretch")
    st.caption(
        "O diagnostico mostra apenas a origem de cada segredo, nunca o valor. "
        "Nenhum numero desta tela foi recalculado."
    )
    if st.button("tentar de novo"):
        db.limpar_cache()
        st.rerun()


# --------------------------------------------------------------------------
# Barra lateral
# --------------------------------------------------------------------------


def _aplicar_preset() -> None:
    escolha = st.session_state.get("preset_periodo", "Ultimos 12m")
    if escolha == "Personalizado":
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
        st.session_state["comp_ini"], st.session_state["comp_fim"] = PRESETS_PERIODO["Ultimos 12m"]

    # "" porque o Streamlit serve a pagina default na raiz, com url_path vazio.
    if pagina in ("guia", ""):
        # O Guia nao consulta o banco: mostrar filtros ali e prometer um efeito que
        # nao existe. Os valores escolhidos sobrevivem no session_state e voltam a
        # aparecer -- e a valer -- assim que o usuario entra numa pagina de dados.
        return _filtros_do_estado(clientes)

    with st.sidebar:
        st.markdown("### Filtros")

        st.radio(
            "Período de competência",
            options=list(PRESETS_PERIODO),
            key="preset_periodo",
            on_change=_aplicar_preset,
            help="O período move o eixo do tempo e o recorte dos fatos. Ele NÃO move a janela "
                 "de 12 meses da inadimplência nem a foto da carteira.",
        )
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

        st.divider()
        if pagina == "inadimplencia":
            # Na pagina de inadimplencia o seletor de foto e o controle principal
            # e vive no cabecalho da propria pagina. Renderizar duas vezes o
            # mesmo widget quebraria o estado, entao aqui a barra lateral so ecoa.
            data_ref = st.session_state.get("ref_data", config.DATA_EXTRACAO)
            st.caption(f"Data da foto: **{fmt.data_br(data_ref)}** (no topo da página)")
        else:
            data_ref = ui.seletor_data_referencia(
                valor=st.session_state.get("ref_data", config.DATA_EXTRACAO),
                minimo=date(2024, 12, 31),
                maximo=config.DATA_EXTRACAO,
                chave="ref",
                rotulo="Data da foto (independente do período)",
            )

        st.divider()
        segmentos = st.multiselect(
            "Segmento", options=opcoes.get("segmentos", []), key="f_segmentos",
            format_func=rot.valor,
        )
        portes = st.multiselect(
            "Porte", options=opcoes.get("portes", []), key="f_portes", format_func=rot.valor,
        )
        ratings_opcoes = list(opcoes.get("ratings", [])) + [_SEM_RATING]
        ratings = st.multiselect("Rating de crédito", options=ratings_opcoes, key="f_ratings")
        tipos_contrato = st.multiselect(
            "Tipo de contrato", options=opcoes.get("tipos_contrato", []),
            key="f_tipos_contrato", format_func=rot.valor,
        )

        nomes = dict(zip(clientes["nome_cliente"], clientes["id_cliente"])) if not clientes.empty else {}
        escolhidos = st.multiselect(
            "Cliente", options=sorted(nomes), placeholder="busque pelo nome", key="f_clientes",
            help="Recorte de cliente desliga a atribuição do custo de veículo parado: ele não "
                 "pertence a contrato nenhum, e por isso não pertence a cliente nenhum.",
        )

        # Nao ha expander de "versoes do orcamento" nem de politica de filtros aqui:
        # o app usa sempre a versao vigente (o usuario nao escolhe), e a tabela de
        # "qual filtro nao afeta o que" vive no Guia, onde e explicada. Repetir as
        # duas na barra lateral so competia com os filtros de verdade.
        st.divider()
        if st.button("limpar filtros", width="stretch"):
            for chave in (
                "preset_periodo", "comp_ini", "comp_fim", "f_segmentos", "f_portes",
                "f_ratings", "f_tipos_contrato", "f_clientes", "faixa_aging",
                "meta_indicador", "meta_por_segmento",
            ):
                st.session_state.pop(chave, None)
            st.rerun()
        if st.button("atualizar dados (limpar cache)", width="stretch"):
            db.limpar_cache()
            st.cache_data.clear()
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
    st.session_state["versao_orcamento"] = _rotulo_versao(filtros.fim.year)
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
    st.session_state["versao_orcamento"] = _rotulo_versao(filtros.fim.year)
    return filtros


def _rotulo_versao(ano: int) -> str:
    """Rotulo da versao vigente do orcamento do ano, para o rodape de proveniencia."""
    try:
        df = _versoes(ano)
        vigente = df[df["eh_versao_vigente"]]
        if not vigente.empty:
            return f"{rot.valor(vigente.iloc[0]['versao_meta'])} (vigente)"
    except Exception:  # noqa: BLE001 - rodape nunca derruba a pagina
        pass
    return "versão vigente"


# --------------------------------------------------------------------------
# Navegacao
# --------------------------------------------------------------------------


#: Uma pergunta por pagina, declarada no titulo. O Guia e a pagina inicial:
#: quem abre o relatorio pela primeira vez comeca sabendo o que vai encontrar.
PAGINAS = [
    st.Page("views/pagina_0_guia.py", title="Guia",
            icon=":material/menu_book:", url_path="guia", default=True),
    # O menu leva o nome curto (é um dashboard, não um sumário); a pergunta de
    # negócio continua sendo o titulo dentro da pagina.
    st.Page("views/pagina_1_metas.py", title="Metas",
            icon=":material/flag:", url_path="metas"),
    st.Page("views/pagina_2_faturamento_recebimento.py",
            title="Faturamento e Recebimento",
            icon=":material/receipt_long:", url_path="faturamento-recebimento"),
    st.Page("views/pagina_3_inadimplencia.py", title="Inadimplência",
            icon=":material/gavel:", url_path="inadimplencia"),
    st.Page("views/pagina_4_custos.py", title="Custos",
            icon=":material/payments:", url_path="custos"),
]


def main() -> None:
    # Primeira coisa do rerun: o <style> do app e recriado a cada redesenho, entao
    # o guard de estilos() -- que vive em session_state e sobrevive ao rerun --
    # precisa ser zerado aqui. Sem isto a pagina volta sem CSS ao trocar de pagina
    # ou mexer num filtro, e so o F5 (sessao nova) devolve o estilo.
    ui.reiniciar_estilos()

    estado = db.verificar_conexao()
    if not estado.ok:
        tela_sem_banco(estado.mensagem)
        st.stop()

    pagina = st.navigation(PAGINAS, position="sidebar")
    try:
        opcoes, clientes = _opcoes(), _clientes()
    except Exception as exc:  # noqa: BLE001 - boot da sidebar
        tela_sem_banco(getattr(exc, "mensagem_usuario", "Nao foi possivel falar com o banco."))
        st.stop()

    barra_lateral(opcoes, clientes, pagina=pagina.url_path)
    pagina.run()


main()
