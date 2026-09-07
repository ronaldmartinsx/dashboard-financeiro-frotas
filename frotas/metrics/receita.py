"""Metricas de receita: faturamento, receita liquida e YoY.

Escopo do modulo (reduzido): **faturamento**. Carteira contratual (MRR, churn,
contratos ativos) saiu do projeto, e cancelamento deixou de ter secao propria --
vira nota de rodape do visual de faturamento, alimentada por ``valor_cancelado``
e ``pct_cancelado``, que continuam em :func:`resumo`,
:func:`faturamento_por_competencia` e :func:`faturamento_por_ano`.

**A logica point-in-time de cancelamento nao saiu.** Ela e a armadilha 1 e o que
separa ``faturamento_bruto`` de ``faturamento_valido``: um titulo cancelado em
out/2025 conta como valido numa foto de set/2025 e nao conta numa de dez/2025.

Definicoes canonicas (reproduzem os numeros publicados no briefing):

* **Faturamento bruto** = ``sum(valor_bruto)`` por competencia, *incluindo*
  titulos cancelados. 2024 = 29,79 mi · 2025 = 35,02 mi · 2026 (8m) = 24,62 mi.
* **Faturamento valido** = faturamento bruto com o filtro point-in-time de
  cancelamento na data de referencia (armadilha 1). Numa foto de hoje ele e o
  bruto menos os cancelamentos; numa foto de set/2025 os cancelamentos de out/2025
  ainda contam como validos.
* **Receita liquida** = ``sum(valor_liquido)``, tambem incluindo cancelados
  (27,95 / 32,78 / 23,05 mi). E o denominador da margem publicada -- por isso o
  padrao de :class:`Filtros` e ``incluir_cancelados=True``. Excluindo cancelados
  a serie cai para 26,96 / 30,74 / 22,59 mi, que **nao** e o numero publicado.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from frotas import config, db
from frotas.filtros import Filtros, clausula_valida_em, condicoes_titulos

_DE = """
from public.titulos_receber t
join public.clientes cl on cl.id_cliente = t.id_cliente
join public.contratos ct on ct.id_contrato = t.id_contrato
"""

_MEDIDAS = """
       sum(t.valor_bruto)::float8                              as faturamento_bruto,
       sum(t.valor_bruto) filter (where {valida})::float8      as faturamento_valido,
       sum(t.valor_liquido)::float8                            as receita_liquida,
       sum(t.valor_impostos)::float8                           as impostos,
       coalesce(sum(t.valor_bruto) filter
                (where not {valida}), 0)::float8               as valor_cancelado,
       count(*)                                                as qtd_titulos
"""

#: Dimensoes aceitas por :func:`faturamento_por_dimensao`.
DIMENSOES: dict[str, tuple[str, str]] = {
    "segmento": ("cl.segmento", "segmento"),
    "porte": ("cl.porte", "porte"),
    "rating": ("cl.rating_credito", "rating_credito"),
    "uf": ("cl.uf", "uf"),
    "cliente": ("cl.nome_cliente", "nome_cliente"),
    "tipo_receita": ("t.tipo_receita", "tipo_receita"),
    "tipo_contrato": ("ct.tipo_contrato", "tipo_contrato"),
    "status_contrato": ("ct.status_contrato", "status_contrato"),
    "contrato": ("t.id_contrato", "id_contrato"),
}

Dimensao = Literal[
    "segmento", "porte", "rating", "uf", "cliente", "tipo_receita",
    "tipo_contrato", "status_contrato", "contrato", "categoria_veiculo",
]


def _medidas() -> str:
    return _MEDIDAS.format(valida=clausula_valida_em("t"))


def resumo(filtros: Filtros) -> pd.DataFrame:
    """Linha unica de KPIs de receita para o topo da pagina.

    Colunas: ``faturamento_bruto``, ``faturamento_valido``, ``receita_liquida``,
    ``impostos``, ``valor_cancelado``, ``pct_cancelado``, ``qtd_titulos``,
    ``ticket_medio``.

    Armadilha tratada: o cancelamento e avaliado em ``filtros.ref``, nao pelo
    ``status_titulo`` gravado (que e a foto de 2026-08-31).
    """
    cond, params = condicoes_titulos(filtros)
    params["ref"] = filtros.ref
    df = db.consultar(f"select{_medidas()}{_DE}where 1=1{cond}", params, ttl=config.TTL_FATOS)
    df["pct_cancelado"] = 100.0 * df["valor_cancelado"] / df["faturamento_bruto"].replace(0, pd.NA)
    df["ticket_medio"] = df["faturamento_bruto"] / df["qtd_titulos"].replace(0, pd.NA)
    return df


def faturamento_por_competencia(filtros: Filtros) -> pd.DataFrame:
    """Serie mensal de faturamento por **competencia** (nao por emissao).

    Colunas: ``competencia`` (date, dia 1), ``ano_mes``, ``ano``,
    ``faturamento_bruto``, ``faturamento_valido``, ``receita_liquida``,
    ``impostos``, ``valor_cancelado``, ``qtd_titulos``.

    Armadilha tratada: competencia e o mes de servico; emissao acontece no 1o dia
    util seguinte. Agrupar por ``data_emissao`` desloca a serie em um mes.
    """
    cond, params = condicoes_titulos(filtros)
    params["ref"] = filtros.ref
    sql = f"""
    select t.competencia,
           to_char(t.competencia, 'YYYY-MM') as ano_mes,
           extract(year from t.competencia)::int as ano,
           {_medidas().strip()}
    {_DE}
    where 1=1{cond}
    group by 1, 2, 3
    order by 1
    """
    return db.consultar(sql, params, ttl=config.TTL_FATOS)


def faturamento_por_ano(filtros: Filtros) -> pd.DataFrame:
    """Faturamento consolidado por ano de competencia.

    Colunas: ``ano``, ``meses`` (quantos meses de competencia o ano tem no
    recorte), ``eh_parcial``, ``faturamento_bruto``, ``faturamento_valido``,
    ``receita_liquida``, ``impostos``, ``valor_cancelado``, ``qtd_titulos``.

    Armadilha tratada (7): ``eh_parcial`` marca 2026, que so tem 8 meses. Nunca
    compare um ano parcial com um ano cheio sem olhar essa coluna.
    """
    cond, params = condicoes_titulos(filtros)
    params["ref"] = filtros.ref
    sql = f"""
    select extract(year from t.competencia)::int as ano,
           count(distinct t.competencia)         as meses,
           {_medidas().strip()}
    {_DE}
    where 1=1{cond}
    group by 1
    order by 1
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    df["eh_parcial"] = df["meses"] < 12
    return df


def faturamento_por_dimensao(
    filtros: Filtros, dimensao: Dimensao = "segmento", limite: int | None = None
) -> pd.DataFrame:
    """Faturamento quebrado por uma dimensao de cliente, contrato ou receita.

    Args:
        dimensao: uma chave de :data:`DIMENSOES` ou ``"categoria_veiculo"``
            (que delega para :func:`faturamento_por_categoria_veiculo`, com rateio).
        limite: se informado, devolve so os N maiores por faturamento bruto.

    Colunas: a coluna da dimensao + ``faturamento_bruto``, ``faturamento_valido``,
    ``receita_liquida``, ``impostos``, ``valor_cancelado``, ``qtd_titulos``,
    ``participacao_pct``.
    """
    if dimensao == "categoria_veiculo":
        return faturamento_por_categoria_veiculo(filtros)
    if dimensao not in DIMENSOES:
        raise ValueError(f"dimensao invalida: {dimensao!r}. Use uma de {sorted(DIMENSOES)}.")
    expressao, rotulo = DIMENSOES[dimensao]
    cond, params = condicoes_titulos(filtros)
    params["ref"] = filtros.ref
    sql = f"""
    select {expressao} as {rotulo},
           {_medidas().strip()}
    {_DE}
    where 1=1{cond}
    group by 1
    order by faturamento_bruto desc
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    total = df["faturamento_bruto"].sum()
    df["participacao_pct"] = 100.0 * df["faturamento_bruto"] / total if total else 0.0
    return df.head(limite) if limite else df


def faturamento_por_categoria_veiculo(filtros: Filtros) -> pd.DataFrame:
    """Faturamento **rateado** por categoria de veiculo.

    Um titulo nao tem veiculo -- tem contrato. O valor e dividido em partes iguais
    entre os veiculos alocados ao contrato **na competencia do titulo**
    (``data_alocacao <= fim do mes`` e ``data_devolucao`` nula ou ``>= inicio do
    mes``). Contrato sem alocacao vigente no mes cai no fallback: rateia entre
    todos os veiculos que ja passaram pelo contrato.

    Colunas: ``categoria``, ``faturamento_bruto_rateado``,
    ``receita_liquida_rateada``, ``faturamento_valido_rateado``,
    ``qtd_veiculos``, ``participacao_pct``. O sufixo ``_rateado`` e proposital:
    e aproximacao, nao fato contabil.
    """
    cond, params = condicoes_titulos(filtros)
    params["ref"] = filtros.ref
    cond_categoria = ""
    if filtros.categorias_veiculo:
        params["categorias_veiculo"] = filtros.categorias_veiculo
        cond_categoria = "where v.categoria in :categorias_veiculo"
    sql = f"""
    with base as (
        select t.id_titulo, t.id_contrato, t.competencia, t.valor_bruto,
               t.valor_liquido, t.data_cancelamento
        {_DE}
        where 1=1{cond}
    ),
    vigentes as (
        select distinct b.id_titulo, a.id_veiculo
        from base b
        join public.alocacoes_veiculo a on a.id_contrato = b.id_contrato
         and a.data_alocacao <= (b.competencia + interval '1 month' - interval '1 day')::date
         and (a.data_devolucao is null or a.data_devolucao >= b.competencia)
    ),
    fallback as (
        select distinct b.id_titulo, a.id_veiculo
        from base b
        join public.alocacoes_veiculo a on a.id_contrato = b.id_contrato
        where not exists (select 1 from vigentes w where w.id_titulo = b.id_titulo)
    ),
    todos as (
        select * from vigentes union all select * from fallback
    ),
    pesos as (
        select id_titulo, id_veiculo,
               1.0 / count(*) over (partition by id_titulo) as peso
        from todos
    )
    select v.categoria,
           sum(b.valor_bruto * p.peso)::float8   as faturamento_bruto_rateado,
           sum(b.valor_liquido * p.peso)::float8 as receita_liquida_rateada,
           sum(b.valor_bruto * p.peso) filter
               (where b.data_cancelamento is null
                   or b.data_cancelamento > cast(:ref as date))::float8
                                                 as faturamento_valido_rateado,
           count(distinct p.id_veiculo)          as qtd_veiculos
    from pesos p
    join base b on b.id_titulo = p.id_titulo
    join public.veiculos v on v.id_veiculo = p.id_veiculo
    {cond_categoria}
    group by 1
    order by 2 desc
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    total = df["faturamento_bruto_rateado"].sum()
    df["participacao_pct"] = 100.0 * df["faturamento_bruto_rateado"] / total if total else 0.0
    return df


def yoy_mensal(filtros: Filtros) -> pd.DataFrame:
    """Faturamento mes a mes com o mesmo mes do ano anterior ao lado.

    Colunas: ``competencia``, ``ano_mes``, ``ano``, ``mes``,
    ``faturamento_bruto``, ``faturamento_bruto_ano_anterior``,
    ``variacao_abs``, ``variacao_pct``.

    Armadilha tratada (5, efeito base): 2024 nao tem ano anterior no dataset --
    esses meses vem com ``NaN``, nunca com zero. Zero produziria variacao de
    -100% e um grafico que mente.
    """
    cond, params = condicoes_titulos(filtros)
    params["ref"] = filtros.ref
    sql = f"""
    with mensal as (
        select t.competencia,
               sum(t.valor_bruto)::float8 as faturamento_bruto,
               sum(t.valor_liquido)::float8 as receita_liquida
        {_DE}
        where 1=1{cond}
        group by 1
    )
    select m.competencia,
           to_char(m.competencia, 'YYYY-MM') as ano_mes,
           extract(year from m.competencia)::int as ano,
           extract(month from m.competencia)::int as mes,
           m.faturamento_bruto,
           a.faturamento_bruto as faturamento_bruto_ano_anterior,
           m.receita_liquida,
           a.receita_liquida as receita_liquida_ano_anterior
    from mensal m
    left join mensal a
           on a.competencia = (m.competencia - interval '12 months')::date
    order by 1
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    anterior = df["faturamento_bruto_ano_anterior"]
    df["variacao_abs"] = df["faturamento_bruto"] - anterior
    df["variacao_pct"] = 100.0 * df["variacao_abs"] / anterior.where(anterior != 0)
    return df


def yoy_anual(filtros: Filtros) -> pd.DataFrame:
    """Comparacao anual com a correcao de periodo parcial (armadilha 7).

    Colunas: ``ano``, ``meses``, ``eh_parcial``, ``faturamento_bruto``,
    ``receita_liquida``, ``faturamento_bruto_ano_anterior``, ``variacao_pct``
    (ano cheio contra ano cheio) e ``variacao_pct_comparavel`` -- esta ultima
    compara **os mesmos meses** do ano anterior.

    Para 2026 (8 meses), ``variacao_pct`` contra o ano cheio de 2025 diz -30%,
    o que e falso; ``variacao_pct_comparavel`` compara jan-ago com jan-ago.
    """
    cond, params = condicoes_titulos(filtros)
    params["ref"] = filtros.ref
    sql = f"""
    with mensal as (
        select t.competencia,
               extract(year from t.competencia)::int as ano,
               extract(month from t.competencia)::int as mes,
               sum(t.valor_bruto)::float8 as bruto,
               sum(t.valor_liquido)::float8 as liquido
        {_DE}
        where 1=1{cond}
        group by 1, 2, 3
    ),
    anual as (
        select ano, count(*) as meses, max(mes) as ultimo_mes,
               sum(bruto) as faturamento_bruto, sum(liquido) as receita_liquida
        from mensal group by 1
    )
    select a.ano, a.meses, a.ultimo_mes,
           a.faturamento_bruto, a.receita_liquida,
           p.faturamento_bruto as faturamento_bruto_ano_anterior,
           (select sum(m.bruto) from mensal m
             where m.ano = a.ano - 1 and m.mes <= a.ultimo_mes)::float8
               as faturamento_bruto_ano_anterior_comparavel
    from anual a
    left join anual p on p.ano = a.ano - 1
    order by a.ano
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    df["eh_parcial"] = df["meses"] < 12
    ant = df["faturamento_bruto_ano_anterior"]
    df["variacao_pct"] = 100.0 * (df["faturamento_bruto"] - ant) / ant.where(ant != 0)
    comp = df["faturamento_bruto_ano_anterior_comparavel"]
    df["variacao_pct_comparavel"] = (
        100.0 * (df["faturamento_bruto"] - comp) / comp.where(comp != 0)
    )
    return df.drop(columns=["ultimo_mes"])


def _cancelamentos_por_motivo(filtros: Filtros) -> pd.DataFrame:
    """Cancelamentos por motivo -- **privada**: so alimenta o alerta A19.

    Cancelamento deixou de ter secao propria no app (vira nota de rodape do
    visual de faturamento, alimentada por ``valor_cancelado`` / ``pct_cancelado``
    de :func:`resumo` e :func:`faturamento_por_competencia`). A quebra por motivo
    sobreviveu apenas como dependencia de ``alertas.A19`` (cancelamento por falha
    de processo), e por isso e privada. **A logica point-in-time de cancelamento
    dentro do faturamento valido continua publica e essencial** -- e a armadilha 1.

    Colunas: ``motivo_cancelamento``, ``valor_bruto``, ``qtd_titulos``,
    ``participacao_pct`` (sobre o total cancelado), ``pct_do_faturamento``.

    Definicao: conta pelo **ano de competencia** do titulo, nao pelo ano do
    cancelamento. Por competencia o percentual anual da 3,53 / 6,23 / 1,97%,
    proximo mas nao identico aos 4,0 / 6,0 / 2,0% do dicionario (a leitura por
    ano de cancelamento daria 1,22 / 5,45 / 5,88% e se afasta mais). Os valores
    absolutos batem; a divergencia e de definicao e esta em
    ``docs/02_arquitetura.md``.
    """
    cond, params = condicoes_titulos(filtros, com_cancelados=True)
    sql = f"""
    with total as (
        select sum(t.valor_bruto)::float8 as faturamento_bruto
        {_DE}
        where 1=1{cond}
    )
    select t.motivo_cancelamento,
           sum(t.valor_bruto)::float8 as valor_bruto,
           count(*) as qtd_titulos,
           (100.0 * sum(t.valor_bruto) / nullif((select faturamento_bruto from total), 0))::float8
               as pct_do_faturamento
    {_DE}
    where t.data_cancelamento is not null{cond}
    group by 1
    order by 2 desc
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    total = df["valor_bruto"].sum()
    df["participacao_pct"] = 100.0 * df["valor_bruto"] / total if total else 0.0
    return df


def top_clientes(filtros: Filtros, limite: int = 10) -> pd.DataFrame:
    """Maiores clientes por faturamento bruto no periodo.

    Colunas: ``id_cliente``, ``nome_cliente``, ``segmento``, ``porte``,
    ``rating_credito``, ``faturamento_bruto``, ``receita_liquida``,
    ``qtd_titulos``, ``participacao_pct``.
    """
    cond, params = condicoes_titulos(filtros)
    sql = f"""
    select cl.id_cliente, cl.nome_cliente, cl.segmento, cl.porte, cl.rating_credito,
           sum(t.valor_bruto)::float8   as faturamento_bruto,
           sum(t.valor_liquido)::float8 as receita_liquida,
           count(*)                     as qtd_titulos
    {_DE}
    where 1=1{cond}
    group by 1, 2, 3, 4, 5
    order by faturamento_bruto desc
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    total = df["faturamento_bruto"].sum()
    df["participacao_pct"] = 100.0 * df["faturamento_bruto"] / total if total else 0.0
    return df.head(limite)

