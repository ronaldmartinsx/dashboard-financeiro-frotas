"""Configuracao e carregamento de segredos do data app de frotas.

Precedencia de segredos, do mais forte para o mais fraco:

1. ``st.secrets``      -- usado no deploy (Streamlit Community Cloud / container).
2. variavel de ambiente -- usado em CI e em execucao headless dos scripts.
3. ``.env`` na raiz     -- conveniencia de desenvolvimento local; nunca versionado.

Nenhum valor de credencial e impresso, logado, formatado em mensagem de erro ou
escrito em arquivo por este modulo. As funcoes de diagnostico devolvem apenas a
*origem* do segredo, nunca o conteudo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Final

# --------------------------------------------------------------------------
# Constantes de negocio (fixas pelo dataset, ver docs/00_briefing_tecnico.md)
# --------------------------------------------------------------------------

#: Data de extracao simulada do dataset. Nenhum pagamento existe depois dela e o
#: ``status_titulo`` gravado no banco e uma foto exatamente desta data.
DATA_EXTRACAO: Final[date] = date(2026, 8, 31)

#: Primeira e ultima competencia com fato no banco (competencia e sempre dia 1).
COMPETENCIA_MIN: Final[date] = date(2024, 1, 1)
COMPETENCIA_MAX: Final[date] = date(2026, 8, 1)

#: Carencia da metrica de inadimplencia: vencido ha mais de N dias.
DIAS_CARENCIA_INADIMPLENCIA: Final[int] = 30

#: Janela do denominador da inadimplencia (meses de competencia).
MESES_JANELA_INADIMPLENCIA: Final[int] = 12

#: Faixas de aging da carteira, em dias corridos de atraso.
FAIXAS_AGING: Final[tuple[str, ...]] = (
    "A vencer", "1-30d", "31-60d", "61-90d", "91-180d", "180+d",
)

# --------------------------------------------------------------------------
# TTLs de cache (segundos). Dataset e estatico -- TTL longo e seguro.
# --------------------------------------------------------------------------
#
# As constantes de pool, timeout e application_name sairam junto com a conexao
# ao Postgres: o app le arquivos locais e nao tem servidor para negociar.

TTL_DIMENSOES: Final[int] = 24 * 60 * 60   # listas de filtro: 24 h
TTL_FATOS: Final[int] = 60 * 60            # agregacoes de fato: 1 h
TTL_PESADO: Final[int] = 6 * 60 * 60       # series point-in-time: 6 h

#: Nomes de segredo, usados **so** por ``scripts/exportar_dados.py``. O app em si
#: nao le credencial nenhuma desde que passou a consultar o snapshot local.
CHAVE_DSN: Final[str] = "PG_DSN"
CHAVE_SUPABASE_URL: Final[str] = "SUPABASE_URL"
CHAVE_SUPABASE_KEY: Final[str] = "SUPABASE_PUBLISHABLE_KEY"

_RAIZ: Final[Path] = Path(__file__).resolve().parent.parent
_CAMINHO_DOTENV: Final[Path] = _RAIZ / ".env"


class CredencialAusente(RuntimeError):
    """Segredo obrigatorio nao encontrado em nenhuma das origens suportadas.

    A mensagem descreve a *origem esperada*, nunca o valor procurado.
    """


@dataclass(frozen=True)
class OrigemSegredo:
    """De onde um segredo veio -- sem o valor. Serve para a tela de diagnostico."""

    nome: str
    origem: str | None  # "st.secrets" | "ambiente" | ".env" | None

    @property
    def presente(self) -> bool:
        return self.origem is not None


def _ler_streamlit_secrets(nome: str) -> str | None:
    """Le ``st.secrets[nome]`` sem explodir fora de um runtime Streamlit."""
    try:
        import streamlit as st
    except Exception:  # streamlit ausente (ex.: script puro em CI)
        return None
    try:
        # st.secrets levanta StreamlitSecretNotFoundError quando nao ha arquivo.
        valor = st.secrets.get(nome)  # type: ignore[union-attr]
    except Exception:
        return None
    if valor is None:
        # Tambem aceitamos segredos aninhados em uma secao [conexao].
        try:
            secao = st.secrets.get("conexao")  # type: ignore[union-attr]
            valor = secao.get(nome) if secao is not None else None
        except Exception:
            valor = None
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


@lru_cache(maxsize=1)
def _ler_dotenv() -> dict[str, str]:
    """Carrega o ``.env`` da raiz *sem* poluir ``os.environ``.

    Devolve dicionario vazio se o arquivo nao existir (caso do deploy).
    """
    if not _CAMINHO_DOTENV.exists():
        return {}
    try:
        from dotenv import dotenv_values

        return {k: v for k, v in dotenv_values(_CAMINHO_DOTENV).items() if v}
    except Exception:
        # Fallback minimo, para nao depender de python-dotenv em runtime enxuto.
        dados: dict[str, str] = {}
        for linha in _CAMINHO_DOTENV.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valor = valor.strip().strip('"').strip("'")
            if valor:
                dados[chave.strip()] = valor
        return dados


def obter_segredo(nome: str, padrao: str | None = None) -> str | None:
    """Devolve o segredo ``nome`` respeitando a precedencia documentada.

    Nunca levanta por ausencia -- use :func:`obter_dsn` quando o segredo for
    obrigatorio. Nunca registra o valor em log.
    """
    valor = _ler_streamlit_secrets(nome)
    if valor:
        return valor
    valor = os.environ.get(nome)
    if valor and valor.strip():
        return valor.strip()
    valor = _ler_dotenv().get(nome)
    if valor and valor.strip():
        return valor.strip()
    return padrao


def origem_segredo(nome: str) -> OrigemSegredo:
    """Diz de qual origem o segredo veio, **sem** devolver o valor."""
    if _ler_streamlit_secrets(nome):
        return OrigemSegredo(nome, "st.secrets")
    bruto = os.environ.get(nome)
    if bruto and bruto.strip():
        return OrigemSegredo(nome, "ambiente")
    if _ler_dotenv().get(nome):
        return OrigemSegredo(nome, ".env")
    return OrigemSegredo(nome, None)


def diagnostico_segredos() -> list[OrigemSegredo]:
    """Inventario seguro para a UI: quais segredos existem e de onde vieram."""
    return [origem_segredo(n) for n in (CHAVE_DSN, CHAVE_SUPABASE_URL, CHAVE_SUPABASE_KEY)]


def obter_dsn() -> str:
    """DSN Postgres do pooler do Supabase.

    Raises:
        CredencialAusente: quando ``PG_DSN`` nao esta em nenhuma origem. A
            mensagem explica onde configurar, sem citar valores.
    """
    dsn = obter_segredo(CHAVE_DSN)
    if not dsn:
        raise CredencialAusente(
            "Credencial de banco ausente: defina PG_DSN em .streamlit/secrets.toml "
            "(deploy), na variavel de ambiente PG_DSN, ou no arquivo .env da raiz "
            "(desenvolvimento local). Consulte docs/02_arquitetura.md, secao Seguranca."
        )
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise CredencialAusente(
            "PG_DSN encontrado mas com formato inesperado: esperado um DSN "
            "'postgresql://...'. Verifique o segredo (o valor nao e exibido)."
        )
    return dsn
