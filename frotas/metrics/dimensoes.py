"""Listas de dominio para os filtros da UI.

Tudo aqui e cacheado com TTL longo (24 h): sao dominios enumerados de um dataset
estatico. Nenhuma funcao deste modulo aceita :class:`Filtros` -- listas de filtro
mostram o dominio completo, senao o usuario fica preso num recorte vazio.
"""

from __future__ import annotations

import pandas as pd

from frotas import config, db


def listar_segmentos() -> list[str]:
    """Os 8 segmentos de ``clientes.segmento``."""
    return list(db.valores_distintos("clientes", "segmento"))


def listar_portes() -> list[str]:
    """Grande / Medio / PME."""
    return list(db.valores_distintos("clientes", "porte"))


def listar_ratings() -> list[str]:
    """Ratings de credito A / B / C / D."""
    return list(db.valores_distintos("clientes", "rating_credito"))


def listar_ufs() -> list[str]:
    """UFs presentes na base de clientes."""
    return list(db.valores_distintos("clientes", "uf"))


def listar_categorias_veiculo() -> list[str]:
    """As 8 categorias de ``veiculos.categoria``."""
    return list(db.valores_distintos("veiculos", "categoria"))


def listar_tipos_receita() -> list[str]:
    """Locacao, KM Excedente, Avaria, Multa de Transito, Multa Rescisoria, Servicos Adicionais."""
    return list(db.valores_distintos("titulos_receber", "tipo_receita"))


def listar_tipos_contrato() -> list[str]:
    """Os 4 tipos de ``contratos.tipo_contrato``."""
    return list(db.valores_distintos("contratos", "tipo_contrato"))


def listar_status_contrato() -> list[str]:
    """Ativo / Encerrado / Rescindido."""
    return list(db.valores_distintos("contratos", "status_contrato"))


def listar_categorias_custo() -> list[str]:
    """As 11 categorias de ``custos.categoria_custo``."""
    return list(db.valores_distintos("custos", "categoria_custo"))


def listar_tipos_custo() -> list[str]:
    """Fixo / Variavel / Nao Caixa."""
    return list(db.valores_distintos("custos", "tipo_custo"))


def listar_motivos_cancelamento() -> list[str]:
    """Os 5 motivos de cancelamento de titulo."""
    return list(db.valores_distintos("titulos_receber", "motivo_cancelamento"))


def listar_motivos_baixa() -> list[str]:
    """Baixa Caixa / Cortesia / Glosa / Perda Cobravel."""
    return list(db.valores_distintos("titulos_receber", "motivo_baixa"))


def listar_tipos_meta() -> list[str]:
    """As 6 metricas orcadas em ``metas.tipo_meta``."""
    return list(db.valores_distintos("metas", "tipo_meta"))


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


def intervalo_competencia() -> tuple[pd.Timestamp, pd.Timestamp]:
    """Primeira e ultima competencia com fato no banco (2024-01-01 .. 2026-08-01).

    Vem do banco, nao de constante, para o app nao mentir se a base for recarregada.
    """
    df = db.consultar(
        "select min(competencia) as ini, max(competencia) as fim from public.titulos_receber",
        ttl=config.TTL_DIMENSOES,
    )
    return pd.Timestamp(df.loc[0, "ini"]), pd.Timestamp(df.loc[0, "fim"])


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

    Prefira esta funcao as ``listar_*`` na montagem da sidebar: cada ``listar_*``
    e um round-trip de ~0,5 s ao pooler, e sao 15 dominios. Aqui e um
    ``UNION ALL`` unico com ``distinct`` aplicado no servidor.
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
