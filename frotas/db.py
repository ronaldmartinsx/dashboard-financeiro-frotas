"""Camada de acesso a dados: snapshot local, cache e execucao de SQL parametrizado.

O app **nao fala com o Supabase**. Ele le o snapshot Parquet de ``dados/``, que
``scripts/exportar_dados.py`` gera na mao quando o dataset de origem muda, e
consulta esses arquivos com DuckDB, em processo.

Por que DuckDB e nao pandas: a camada semantica inteira e SQL, e e nela que estao
as armadilhas do dataset (corte point-in-time de cancelamento, janela de 12
competencias, meta por periodo casado). Reescrever isso em pandas jogaria fora as
116 verificacoes que validam exatamente aquele SQL. Com DuckDB o texto das
consultas continua o mesmo que rodava no Postgres, e as verificacoes continuam
verificando a mesma coisa.

Regras que este modulo garante (defesa em profundidade):

* **Somente leitura.** As tabelas sao *views* sobre arquivos Parquet abertos em
  modo leitura, e :func:`consultar` recusa qualquer SQL que nao comece por
  ``SELECT``/``WITH``. Duas barreiras independentes.
* **Sempre parametrizado.** Nenhum valor de filtro entra por f-string; os valores
  viajam como bind params (``:nome``), inclusive listas (``in :segmentos``).
* **Degradacao util.** Snapshot ausente ou corrompido vira :class:`ErroDados` com
  ``mensagem_usuario`` pronta para ``st.error`` -- o app nunca mostra stack trace.

Cache: :func:`obter_conexao` usa ``st.cache_resource`` (uma conexao por processo)
e as consultas usam ``st.cache_data`` em tres faixas de TTL. A chave de cache e
``(sql, params ordenados)`` -- estavel porque os params sao uma tupla ordenada de
pares, nunca um dicionario mutavel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from frotas import config

# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------


class ErroBanco(RuntimeError):
    """Base dos erros da camada de dados, com mensagem pronta para a UI."""

    def __init__(self, mensagem_usuario: str, detalhe: str = "") -> None:
        super().__init__(mensagem_usuario)
        self.mensagem_usuario = mensagem_usuario
        self.detalhe = detalhe


class ErroDados(ErroBanco):
    """O snapshot local nao esta la, ou nao da para abrir."""


class ErroConsulta(ErroBanco):
    """A consulta rodou sobre o snapshot e falhou (SQL ou parametro invalido)."""


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
# Snapshot local
# --------------------------------------------------------------------------

#: Onde os Parquet vivem. Gerados por ``scripts/exportar_dados.py``.
DIRETORIO_DADOS = Path(__file__).resolve().parent.parent / "dados"

#: As tabelas do snapshot. Explicita de proposito: o app so enxerga o que esta
#: aqui, e um arquivo solto em ``dados/`` nao vira tabela por acidente.
TABELAS = (
    "titulos_receber", "custos", "clientes", "contratos",
    "veiculos", "metas", "alocacoes_veiculo", "calendario",
)

#: ``to_char`` nao existe no DuckDB, e as consultas usam nove vezes, sempre com
#: ``'YYYY-MM'``. O macro traduz o formato do Postgres para o do ``strftime`` em
#: vez de reescrever o SQL: o texto das consultas precisa continuar identico ao
#: que rodava no Postgres, senao as 116 verificacoes deixam de verificar aquilo.
_MACRO_TO_CHAR = """
create or replace macro to_char(d, f) as
    strftime(d, replace(replace(replace(f, 'YYYY', '%Y'), 'MM', '%m'), 'DD', '%d'))
"""


@_cache_recurso
def obter_conexao():
    """Conexao DuckDB em processo, com uma view por arquivo do snapshot.

    Uma conexao por processo (``st.cache_resource``). O banco em si e ``:memory:``:
    o que existe em disco sao os Parquet, abertos em leitura. Nao ha servidor, nao
    ha rede e nao ha credencial -- por isso a consulta mais cara do app caiu de
    segundos para milissegundos.

    O schema chama ``public`` porque a camada semantica escreve
    ``from public.titulos_receber``. Manter o prefixo evita mexer em todo o SQL.

    Raises:
        ErroDados: snapshot ausente ou ilegivel.
    """
    try:
        import duckdb
    except ImportError:
        raise ErroDados(
            "A biblioteca duckdb nao esta instalada. Rode: pip install -r requirements.txt",
            detalhe="duckdb ausente",
        ) from None

    faltando = [t for t in TABELAS if not (DIRETORIO_DADOS / f"{t}.parquet").exists()]
    if faltando:
        raise ErroDados(
            "Os dados do projeto nao foram encontrados em dados/. Rode "
            "'python3 scripts/exportar_dados.py' para gerar o snapshot.",
            detalhe=f"faltando: {', '.join(faltando)}",
        )

    try:
        conexao = duckdb.connect(":memory:")
        conexao.execute("create schema if not exists public")
        for tabela in TABELAS:
            caminho = (DIRETORIO_DADOS / f"{tabela}.parquet").as_posix()
            conexao.execute(
                f"create or replace view public.{tabela} as "
                f"select * from read_parquet('{caminho}')"
            )
        conexao.execute(_MACRO_TO_CHAR)
    except Exception as exc:  # noqa: BLE001 - arquivo corrompido, versao de parquet
        raise ErroDados(
            "Os dados do projeto existem mas nao puderam ser abertos. Gere o "
            "snapshot de novo com 'python3 scripts/exportar_dados.py'.",
            detalhe=type(exc).__name__,
        ) from None
    return conexao


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


#: Bind param no estilo SQLAlchemy (``:nome``). O ``(?<!:)`` protege os casts
#: ``::date`` / ``::float8``: ali o segundo dois-pontos vem depois de outro e nao
#: pode virar parametro.
_BIND = re.compile(r"(?<!:):([a-zA-Z_]\w*)")

#: Nomes de parametro que a consulta traduzida realmente referencia. Casa com
#: limite de palavra, para ``$ref`` nao ser confundido com ``$ref_data``.
_USADO = re.compile(r"\$([a-zA-Z_]\w*)")


def _traduzir(sql: str, params: ParamsOrdenados) -> tuple[str, dict[str, Any]]:
    """``:nome`` (SQLAlchemy) -> ``$nome`` (DuckDB), expandindo listas.

    ``in :segmentos`` com uma tupla de tres vira ``in ($segmentos_0, $segmentos_1,
    $segmentos_2)``. A tupla nunca chega vazia: ``frotas.filtros._adicionar`` so
    monta a condicao quando ha valor, entao nao existe o caso de ``in ()``.
    """
    valores: dict[str, Any] = {}
    expandidos: dict[str, str] = {}
    for chave, valor in params:
        if isinstance(valor, tuple):
            nomes = []
            for posicao, item in enumerate(valor):
                nome = f"{chave}_{posicao}"
                valores[nome] = item
                nomes.append(f"${nome}")
            expandidos[chave] = "(" + ", ".join(nomes) + ")"
        else:
            valores[chave] = valor

    def trocar(achado: re.Match[str]) -> str:
        nome = achado.group(1)
        if nome in expandidos:
            return expandidos[nome]
        return f"${nome}" if nome in valores else achado.group(0)

    consulta = _BIND.sub(trocar, sql)
    # Param que a consulta nao usa e **descartado**, nao enviado. A camada de
    # metricas monta os params a partir de um helper comum (`condicoes_titulos`)
    # mais extras, e nem toda consulta usa todo extra -- o SQLAlchemy ignorava o
    # sobrando em silencio, o DuckDB recusa a consulta inteira com "excess
    # parameters". Sem este filtro, cada extra esquecido derruba uma metrica so
    # em producao, e o defeito viaja escondido: foi o que aconteceu com o
    # grafico de comparacao anual.
    usados = set(_USADO.findall(consulta))
    return consulta, {k: v for k, v in valores.items() if k in usados}


def _executar(sql: str, params: ParamsOrdenados) -> pd.DataFrame:
    """Roda a consulta sobre o snapshot. Nao cacheado -- ver :func:`consultar`."""
    validar_sql_leitura(sql)
    consulta, valores = _traduzir(sql, params)
    conexao = obter_conexao()
    try:
        # ``cursor()`` a cada consulta: a conexao e uma so no processo e o
        # Streamlit roda scripts em threads. Sem isso, dois reruns simultaneos
        # disputariam o mesmo resultado aberto.
        return conexao.cursor().execute(consulta, valores).fetch_df()
    except ErroBanco:
        raise
    except Exception as exc:  # noqa: BLE001 - duckdb levanta varios tipos
        texto = str(exc).strip().splitlines()
        raise ErroConsulta(
            "A consulta foi recusada (SQL ou parametro invalido). E um defeito da "
            "camada de metricas, nao uma falha de leitura dos dados.",
            detalhe=texto[0][:200] if texto else type(exc).__name__,
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
class EstadoDados:
    """Resultado da checagem do snapshot, para a tela de boot."""

    ok: bool
    mensagem: str
    origem: str | None = None


def verificar_dados() -> EstadoDados:
    """Confere se o snapshot esta la e responde, sem levantar excecao.

    Roda no boot do app. Onde antes havia um teste de rede contra o pooler --
    a operacao mais lenta da abertura -- hoje ha uma leitura local.
    """
    try:
        linhas = consultar(
            "select count(*) as n from public.titulos_receber", ttl=config.TTL_DIMENSOES
        )
    except ErroBanco as exc:
        return EstadoDados(False, exc.mensagem_usuario, None)
    if linhas.empty or int(linhas.loc[0, "n"]) == 0:
        return EstadoDados(False, "O snapshot de dados esta vazio.", str(DIRETORIO_DADOS))
    return EstadoDados(
        True,
        f"Lendo o snapshot local de dados/ ({int(linhas.loc[0, 'n']):,} títulos).".replace(",", "."),
        str(DIRETORIO_DADOS),
    )


def limpar_cache() -> None:
    """Invalida o cache de consultas (botao 'Atualizar dados' da UI)."""
    for fn in _FAIXAS_CACHE.values():
        limpar = getattr(fn, "clear", None)
        if callable(limpar):
            limpar()
