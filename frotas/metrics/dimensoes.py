"""Listas de dominio para os filtros da UI.

Tudo aqui e cacheado com TTL longo (24 h): sao dominios enumerados de um dataset
estatico. Nenhuma funcao deste modulo aceita :class:`Filtros` -- listas de filtro
mostram o dominio completo, senao o usuario fica preso num recorte vazio.
"""

from __future__ import annotations

import pandas as pd

from frotas import config, db


def listar_clientes() -> pd.DataFrame:
    """Carteira de clientes para o seletor.

    Colunas: ``id_cliente``, ``nome_cliente``, ``segmento``, ``porte``,
    ``rating_credito``, ``uf``, ``limite_credito``.
    """
    return db.consultar(
        """
        select id_cliente, nome_cliente, segmento, porte, rating_credito, uf,
               limite_credito::float8 as limite_credito
        from public.clientes
        order by nome_cliente
        """,
        ttl=config.TTL_DIMENSOES,
    )


def calendario_meses() -> pd.DataFrame:
    """Meses de competencia disponiveis. Colunas: ``competencia``, ``ano_mes``, ``ano``, ``trimestre``."""
    return db.consultar(
        """
        select distinct
               date_trunc('month', c.data)::date as competencia,
               c.ano_mes, c.ano::int as ano, c.trimestre
        from public.calendario c
        where c.data between (select min(competencia) from public.titulos_receber)
                         and cast(:extracao as date)
        order by 1
        """,
        {"extracao": config.DATA_EXTRACAO},
        ttl=config.TTL_DIMENSOES,
    )


_SQL_OPCOES = """
select 'segmentos' as dominio, segmento as valor from public.clientes
union all select 'portes', porte from public.clientes
union all select 'ratings', rating_credito from public.clientes
union all select 'ufs', uf from public.clientes
union all select 'categorias_veiculo', categoria from public.veiculos
union all select 'status_veiculo', status_veiculo from public.veiculos
union all select 'tipos_receita', tipo_receita from public.titulos_receber
union all select 'motivos_cancelamento', motivo_cancelamento from public.titulos_receber
union all select 'motivos_baixa', motivo_baixa from public.titulos_receber
union all select 'formas_pagamento', forma_pagamento from public.titulos_receber
union all select 'tipos_contrato', tipo_contrato from public.contratos
union all select 'status_contrato', status_contrato from public.contratos
union all select 'categorias_custo', categoria_custo from public.custos
union all select 'tipos_custo', tipo_custo from public.custos
union all select 'tipos_meta', tipo_meta from public.metas
"""


def opcoes_filtros() -> dict[str, list[str]]:
    """Todas as listas de filtro em **uma unica** ida ao banco -- o boot da sidebar.

    Chaves: ``segmentos``, ``portes``, ``ratings``, ``ufs``,
    ``categorias_veiculo``, ``status_veiculo``, ``tipos_receita``,
    ``motivos_cancelamento``, ``motivos_baixa``, ``formas_pagamento``,
    ``tipos_contrato``, ``status_contrato``, ``categorias_custo``,
    ``tipos_custo``, ``tipos_meta``.

    E o unico caminho para as listas de dominio: um ``UNION ALL`` com ``distinct``
    aplicado no motor, em vez de um round-trip por dominio.
    """
    df = db.consultar(
        f"select dominio, valor from ({_SQL_OPCOES}) d "
        "where valor is not null group by 1, 2 order by 1, 2",
        ttl=config.TTL_DIMENSOES,
    )
    return {
        dominio: grupo["valor"].tolist()
        for dominio, grupo in df.groupby("dominio", sort=False)
    }
