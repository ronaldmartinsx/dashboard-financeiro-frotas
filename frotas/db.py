"""Camada de acesso a dados: engine, cache e execucao de SQL parametrizado.

Regras que este modulo garante (defesa em profundidade):

* **Somente leitura.** A sessao abre com ``default_transaction_read_only=on`` no
  servidor e :func:`consultar` recusa qualquer SQL que nao comece por
  ``SELECT``/``WITH``. Duas barreiras independentes.
* **Sempre parametrizado.** Nenhum valor de filtro entra por f-string; os valores
  viajam como bind params (``:nome``), inclusive listas (``in :segmentos``).
* **Degradacao util.** Falta de credencial ou banco inacessivel viram
  :class:`ErroBanco` com ``mensagem_usuario`` pronta para ``st.error`` -- o app
  nunca mostra stack trace nem trecho de credencial.

Cache: :func:`obter_engine` usa ``st.cache_resource`` (um engine por processo) e
as consultas usam ``st.cache_data`` em tres faixas de TTL. A chave de cache e
``(sql, params ordenados)`` -- estavel porque os params sao uma tupla ordenada de
pares, nunca um dicionario mutavel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

import pandas as pd

from frotas import config
from frotas.config import CredencialAusente

# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------


class ErroBanco(RuntimeError):
    """Base dos erros da camada de dados, com mensagem pronta para a UI."""

    def __init__(self, mensagem_usuario: str, detalhe: str = "") -> None:
        super().__init__(mensagem_usuario)
        self.mensagem_usuario = mensagem_usuario
        self.detalhe = detalhe


class ErroConexao(ErroBanco):
    """Nao foi possivel falar com o banco (credencial, rede, pooler fora)."""


class ErroConsulta(ErroBanco):
    """A consulta chegou ao banco e falhou (timeout, SQL invalido, permissao)."""


class SqlNaoPermitido(ErroBanco):
    """A guarda de leitura recusou o SQL antes de qualquer round-trip."""


# --------------------------------------------------------------------------
# Guarda de somente-leitura
# --------------------------------------------------------------------------

_COMENTARIO_LINHA = re.compile(r"--[^\n]*")
_COMENTARIO_BLOCO = re.compile(r"/\*.*?\*/", re.DOTALL)
_INICIO_VALIDO = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_VERBOS_PROIBIDOS = re.compile(
    r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant|revoke|"
    r"copy|vacuum|analyze|reindex|cluster|refresh|call|listen|notify|lock|"
    r"commit|rollback|savepoint|prepare|execute|discard)\b",
    re.IGNORECASE,
)


def _sem_comentarios(sql: str) -> str:
    return _COMENTARIO_BLOCO.sub(" ", _COMENTARIO_LINHA.sub(" ", sql))


def validar_sql_leitura(sql: str) -> None:
    """Recusa qualquer SQL que nao seja uma unica consulta de leitura.

    Verifica, sobre o texto sem comentarios: inicio em ``SELECT``/``WITH``,
    ausencia de verbo de escrita/DDL e ausencia de ``;`` que emende um segundo
    comando. Levanta :class:`SqlNaoPermitido`.
    """
    limpo = _sem_comentarios(sql).strip()
    if not _INICIO_VALIDO.match(limpo):
        raise SqlNaoPermitido(
            "Consulta bloqueada: a camada de dados so executa SELECT/WITH.",
            detalhe="inicio invalido",
        )
    if _VERBOS_PROIBIDOS.search(limpo):
        raise SqlNaoPermitido(
            "Consulta bloqueada: verbo de escrita ou DDL encontrado no SQL.",
            detalhe="verbo proibido",
        )
    if ";" in limpo.rstrip().rstrip(";"):
        raise SqlNaoPermitido(
            "Consulta bloqueada: mais de um comando no mesmo SQL.",
            detalhe="multiplos statements",
        )


# --------------------------------------------------------------------------
# Decoradores de cache -- degradam para no-op fora do Streamlit
# --------------------------------------------------------------------------

try:  # pragma: no cover - depende do ambiente
    import streamlit as _st
except Exception:  # streamlit ausente
    _st = None  # type: ignore[assignment]


def _cache_recurso(fn):
    if _st is None:
        return lru_cache(maxsize=1)(fn)
    return _st.cache_resource(show_spinner=False)(fn)


def _cache_dados(ttl: int):
    def deco(fn):
        if _st is None:
            return lru_cache(maxsize=256)(fn)
        return _st.cache_data(ttl=ttl, show_spinner=False, max_entries=256)(fn)

    return deco


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------


@_cache_recurso
def obter_engine():
    """Engine SQLAlchemy apontando para o pooler do Supabase (modo session).

    Um engine por processo (``st.cache_resource``). Pool deliberadamente pequeno
    -- o pooler e recurso compartilhado do projeto -- com ``pool_pre_ping`` para
    absorver a queda silenciosa de conexao que o pooler faz por ociosidade.

    Raises:
        ErroConexao: credencial ausente ou DSN malformado.
    """
    from sqlalchemy import create_engine, event

    try:
        dsn = config.obter_dsn()
    except CredencialAusente as exc:
        raise ErroConexao(str(exc), detalhe="credencial") from None

    opcoes_sessao = " ".join(
        (
            f"-c statement_timeout={config.TIMEOUT_STATEMENT_MS}",
            f"-c idle_in_transaction_session_timeout={config.TIMEOUT_STATEMENT_MS}",
            "-c default_transaction_read_only=on",
        )
    )
    try:
        engine = create_engine(
            dsn,
            pool_size=config.POOL_TAMANHO,
            max_overflow=config.POOL_OVERFLOW,
            pool_timeout=config.TIMEOUT_POOL_S,
            pool_recycle=config.POOL_RECICLAGEM_S,
            pool_pre_ping=True,
            future=True,
            # AUTOCOMMIT: leitura pura nao precisa de BEGIN/COMMIT explicitos.
            # Economiza duas viagens de rede por consulta (o pooler fica em outra
            # regiao: cada round-trip custa ~240 ms). O read-only continua valendo
            # -- default_transaction_read_only vale para a transacao implicita.
            isolation_level="AUTOCOMMIT",
            connect_args={
                "sslmode": "require",
                "connect_timeout": config.TIMEOUT_CONEXAO_S,
                "application_name": config.NOME_APLICACAO,
                # Honrado numa conexao direta ao Postgres; o Supavisor descarta o
                # startup packet 'options' -- por isso o listener abaixo repete
                # os mesmos ajustes via set_config() ja dentro da sessao.
                "options": opcoes_sessao,
            },
        )
    except Exception as exc:  # DSN sintaticamente invalido, driver ausente...
        raise ErroConexao(
            "Nao foi possivel preparar a conexao com o banco. Verifique o segredo "
            "PG_DSN (o valor nao e exibido) e se psycopg2 esta instalado.",
            detalhe=type(exc).__name__,
        ) from None

    event.listen(engine, "connect", _ajustar_sessao)
    return engine


def _ajustar_sessao(conexao_dbapi, _registro) -> None:
    """Aplica timeouts, ``application_name`` e read-only em cada nova conexao.

    O pooler do Supabase (Supavisor) ignora o parametro de startup ``options``,
    entao os ajustes sao reaplicados aqui, via ``set_config`` parametrizado
    (``SET`` puro nao aceita bind param). ``is_local=false`` faz valer para a
    sessao inteira -- o pooler esta em modo session, entao a conexao e nossa
    ate voltar para o pool.
    """
    with conexao_dbapi.cursor() as cursor:
        cursor.execute(
            "select set_config('application_name', %s, false),"
            "       set_config('statement_timeout', %s, false),"
            "       set_config('idle_in_transaction_session_timeout', %s, false),"
            "       set_config('default_transaction_read_only', 'on', false)",
            (
                config.NOME_APLICACAO,
                str(config.TIMEOUT_STATEMENT_MS),
                str(config.TIMEOUT_STATEMENT_MS),
            ),
        )
    conexao_dbapi.commit()


# --------------------------------------------------------------------------
# Execucao
# --------------------------------------------------------------------------

ParamsOrdenados = tuple[tuple[str, Any], ...]


def _normalizar_params(params: Mapping[str, Any] | None) -> ParamsOrdenados:
    """Dicionario de filtros -> tupla ordenada e hashavel (chave de cache estavel).

    Listas viram tuplas para poderem ser hasheadas e para acionarem o
    ``expanding`` bind do SQLAlchemy (``in :segmentos``).
    """
    if not params:
        return ()
    itens: list[tuple[str, Any]] = []
    for chave, valor in params.items():
        if isinstance(valor, (list, set)):
            valor = tuple(sorted(valor, key=str))
        itens.append((chave, valor))
    return tuple(sorted(itens, key=lambda kv: kv[0]))


def _executar(sql: str, params: ParamsOrdenados) -> pd.DataFrame:
    """Round-trip real ao banco. Nao cacheado -- ver :func:`consultar`."""
    from sqlalchemy import bindparam, text
    from sqlalchemy.exc import DataError, ProgrammingError, SQLAlchemyError

    validar_sql_leitura(sql)
    dicionario = dict(params)
    comando = text(sql)
    expandindo = [
        bindparam(nome, expanding=True)
        for nome, valor in params
        if isinstance(valor, tuple)
    ]
    if expandindo:
        comando = comando.bindparams(*expandindo)

    engine = obter_engine()
    try:
        with engine.connect() as conexao:
            return pd.read_sql_query(comando, conexao, params=dicionario)
    except SQLAlchemyError as exc:
        origem = getattr(exc, "orig", None)
        texto = str(origem or exc)
        if "statement timeout" in texto or "canceling statement" in texto:
            raise ErroConsulta(
                "A consulta passou do tempo limite "
                f"({config.TIMEOUT_STATEMENT_MS // 1000}s). Reduza o periodo do "
                "filtro e tente de novo.",
                detalhe="statement_timeout",
            ) from None
        if "read-only transaction" in texto:
            raise ErroConsulta(
                "Operacao de escrita recusada pelo banco: a sessao do app e "
                "somente leitura.",
                detalhe="read_only",
            ) from None
        if isinstance(exc, (ProgrammingError, DataError)):
            # Erro de SQL ou de tipo de parametro: e bug da camada semantica, nao
            # queda de banco. Nao mascarar como indisponibilidade -- isso mandaria
            # o desenvolvedor procurar problema de rede que nao existe.
            raise ErroConsulta(
                "A consulta foi recusada pelo banco (SQL ou parametro invalido). "
                "E um defeito da camada de metricas, nao uma falha de conexao.",
                detalhe=texto.strip().splitlines()[0][:200] if texto else type(exc).__name__,
            ) from None
        raise ErroConexao(
            "Banco de dados indisponivel no momento. Verifique a conexao e o "
            "segredo PG_DSN; os dados exibidos podem estar desatualizados.",
            detalhe=type(exc).__name__,
        ) from None


@_cache_dados(config.TTL_DIMENSOES)
def _consultar_dimensoes(sql: str, params: ParamsOrdenados) -> pd.DataFrame:
    return _executar(sql, params)


@_cache_dados(config.TTL_FATOS)
def _consultar_fatos(sql: str, params: ParamsOrdenados) -> pd.DataFrame:
    return _executar(sql, params)


@_cache_dados(config.TTL_PESADO)
def _consultar_pesado(sql: str, params: ParamsOrdenados) -> pd.DataFrame:
    return _executar(sql, params)


_FAIXAS_CACHE = {
    config.TTL_DIMENSOES: _consultar_dimensoes,
    config.TTL_FATOS: _consultar_fatos,
    config.TTL_PESADO: _consultar_pesado,
}


def consultar(
    sql: str,
    params: Mapping[str, Any] | None = None,
    ttl: int = config.TTL_FATOS,
) -> pd.DataFrame:
    """Executa uma consulta de leitura parametrizada e devolve um DataFrame.

    E a **unica** porta de leitura do app: toda a camada semantica passa por aqui.

    Args:
        sql: consulta comecando por ``SELECT`` ou ``WITH``. Valores de filtro
            **sempre** como bind params ``:nome`` -- nunca interpolados.
        params: mapa nome -> valor. Listas/tuplas acionam ``expanding`` bind e
            podem ser usadas com ``in :nome``.
        ttl: faixa de cache; use ``config.TTL_DIMENSOES`` (24h, listas de filtro),
            ``config.TTL_FATOS`` (1h, agregacoes) ou ``config.TTL_PESADO`` (6h,
            series point-in-time).

    Returns:
        ``pandas.DataFrame`` com as colunas da consulta.

    Raises:
        SqlNaoPermitido: SQL fora do perfil de leitura.
        ErroConexao / ErroConsulta: com ``mensagem_usuario`` pronta para a UI.
    """
    validar_sql_leitura(sql)
    executor = _FAIXAS_CACHE.get(ttl, _consultar_fatos)
    return executor(sql, _normalizar_params(params))


@dataclass(frozen=True)
class EstadoConexao:
    """Resultado do teste de conectividade, para a barra lateral de diagnostico."""

    ok: bool
    mensagem: str
    origem_credencial: str | None = None


def verificar_conexao() -> EstadoConexao:
    """Testa a conexao sem levantar excecao -- use no boot do app.

    Nunca revela o DSN: informa apenas a origem do segredo (``st.secrets``,
    ``ambiente`` ou ``.env``) e uma mensagem acionavel.
    """
    origem = config.origem_segredo(config.CHAVE_DSN).origem
    if origem is None:
        return EstadoConexao(
            False,
            "Credencial de banco nao configurada. Defina PG_DSN em "
            ".streamlit/secrets.toml, na variavel de ambiente ou no .env local.",
            None,
        )
    try:
        df = consultar("select 1 as ok", ttl=config.TTL_FATOS)
    except ErroBanco as exc:
        return EstadoConexao(False, exc.mensagem_usuario, origem)
    if df.empty:
        return EstadoConexao(False, "O banco respondeu vazio ao teste de conexao.", origem)
    return EstadoConexao(True, f"Conectado ao Supabase (credencial via {origem}).", origem)


def limpar_cache() -> None:
    """Invalida o cache de consultas (botao 'Atualizar dados' da UI)."""
    for fn in _FAIXAS_CACHE.values():
        limpar = getattr(fn, "clear", None)
        if callable(limpar):
            limpar()


def valores_distintos(tabela: str, coluna: str, ttl: int = config.TTL_DIMENSOES) -> Sequence[str]:
    """Lista ordenada de valores distintos de uma coluna de dominio enumerado.

    ``tabela`` e ``coluna`` sao validados contra uma lista branca -- sao os
    unicos identificadores que a camada monta por interpolacao, e por isso nao
    aceitam entrada livre.
    """
    permitido = {
        ("clientes", "segmento"), ("clientes", "porte"), ("clientes", "rating_credito"),
        ("clientes", "uf"), ("veiculos", "categoria"), ("veiculos", "status_veiculo"),
        ("contratos", "tipo_contrato"), ("contratos", "status_contrato"),
        ("titulos_receber", "tipo_receita"), ("titulos_receber", "status_titulo"),
        ("titulos_receber", "motivo_cancelamento"), ("titulos_receber", "motivo_baixa"),
        ("titulos_receber", "forma_pagamento"),
        ("custos", "categoria_custo"), ("custos", "tipo_custo"),
        ("metas", "tipo_meta"), ("metas", "versao_meta"), ("metas", "granularidade"),
    }
    if (tabela, coluna) not in permitido:
        raise SqlNaoPermitido(
            f"Coluna '{tabela}.{coluna}' nao esta na lista branca de dimensoes.",
            detalhe="lista branca",
        )
    sql = (
        f"select distinct {coluna} as valor from public.{tabela} "
        f"where {coluna} is not null order by 1"
    )
    return tuple(consultar(sql, ttl=ttl)["valor"].tolist())
