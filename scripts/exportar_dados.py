"""Exporta o dataset do Supabase para Parquet, dentro do projeto.

E a **unica** parte do repositorio que ainda fala com o Postgres, e ela nao roda
no app: roda na mao, quando o dataset de origem muda. Depois de rodar, o app le
so os arquivos de ``dados/`` e nao precisa de credencial nenhuma.

    python3 scripts/exportar_dados.py

Precisa de ``PG_DSN`` (st.secrets, variavel de ambiente ou ``.env``) e de
``sqlalchemy``/``psycopg2``, que sao dependencias **de desenvolvimento**:
``requirements.txt`` nao as traz, porque o app nao as usa.

O valor do segredo nunca e impresso -- so a origem consultada.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402

from frotas import config  # noqa: E402

#: As oito tabelas do dataset. A lista e explicita, e nao um "todas do schema",
#: para que acrescentar tabela ao banco seja uma decisao e nao um efeito colateral.
TABELAS = (
    "titulos_receber",
    "custos",
    "clientes",
    "contratos",
    "veiculos",
    "metas",
    "alocacoes_veiculo",
    "calendario",
)

DESTINO = RAIZ / "dados"


def main() -> int:
    try:
        dsn = config.obter_dsn()
    except Exception as exc:  # noqa: BLE001 - mensagem, nunca o valor do segredo
        print(f"credencial indisponivel: {exc}")
        return 2

    try:
        from sqlalchemy import create_engine
    except ImportError:
        print("sqlalchemy e psycopg2 sao necessarios so para exportar:")
        print("  python3 -m pip install sqlalchemy psycopg2-binary")
        return 2

    origem = config.origem_segredo(config.CHAVE_DSN).origem
    print(f"Exportando de Supabase (credencial via {origem}) para {DESTINO}/\n")
    DESTINO.mkdir(exist_ok=True)

    engine = create_engine(dsn, connect_args={"sslmode": "require"}, future=True)
    total_linhas = 0
    total_bytes = 0
    with engine.connect() as conexao:
        for tabela in TABELAS:
            df = pd.read_sql_query(f"select * from public.{tabela}", conexao)
            caminho = DESTINO / f"{tabela}.parquet"
            df.to_parquet(caminho, index=False, compression="zstd")
            tamanho = caminho.stat().st_size
            total_linhas += len(df)
            total_bytes += tamanho
            print(f"  {tabela:22} {len(df):>7,} linhas  {len(df.columns):>3} colunas  "
                  f"{tamanho / 1024:>8.1f} KB")

    print(f"\n  {'total':22} {total_linhas:>7,} linhas"
          f"{'':>16}{total_bytes / 1024:>8.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
