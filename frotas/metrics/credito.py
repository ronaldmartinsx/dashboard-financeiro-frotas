"""Metricas de credito: **a posicao atual** da inadimplencia, aging e risco.

Escopo do modulo (reduzido): so a **foto na data de referencia**. Nao ha serie
historica de inadimplencia, nem visao retroativa, nem curva de recuperacao --
essas leituras sairam do projeto. O coracao do eixo e
:func:`inadimplencia_ponto_no_tempo`, e todo o resto sao recortes da mesma foto.

E o modulo mais delicado do app. Tres armadilhas do briefing convergem aqui:

1. **Cancelamento e point-in-time** (armadilha 1). Um titulo cancelado em
   out/2025 nao pode contar como inadimplente numa foto de dez/2025 -- mas
   contava numa foto de set/2025. Sem esse filtro a inadimplencia de jun/2026
   sobe de 9,37% para 18,7%.
2. **Vencido e calculado, nunca lido** (armadilha 2). ``status_titulo`` e a foto
   de 2026-08-31. Para qualquer outra data de referencia, recalcule a partir de
   ``data_vencimento`` / ``data_pagamento`` / ``data_cancelamento``.
3. **Efeito base** (armadilha 5). O denominador e uma janela movel de 12 meses de
   competencia; antes de dez/2024 a janela esta incompleta e o percentual sobe
   por construcao. :func:`inadimplencia_ponto_no_tempo` marca isso em
   ``janela_completa`` -- a UI deve rotular a foto quando a coluna vier ``False``.

**Definicao canonica da inadimplencia > 30d** (reproduz 3,56% em dez/24, 6,47%
em jun/25, 10,20% em dez/25 e 9,37% em jun/26):

* numerador = ``sum(valor_bruto)`` dos titulos com
  ``data_vencimento <= data_ref - 30``, nao pagos e nao cancelados *na data_ref*.
  Titulos baixados **entram** no numerador -- a baixa e decisao interna de
  cobranca, nao recebimento.
* denominador = faturamento bruto dos **ultimos 12 meses de competencia**
  contados de ``data_ref``, tambem com filtro point-in-time de cancelamento.

Nao e "vencido / carteira" nem "vencido / faturado acumulado". As duas variantes
dao numeros diferentes e nenhuma reproduz o publicado.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from frotas import config, db
from frotas.filtros import (
    Filtros,
    clausula_nao_baixado_em,
    clausula_nao_pago_em,
    clausula_valida_em,
    condicoes_titulos,
)

_DE = """
from public.titulos_receber t
join public.clientes cl on cl.id_cliente = t.id_cliente
join public.contratos ct on ct.id_contrato = t.id_contrato
"""

_FAIXA = """
    case when t.data_vencimento > cast(:{p} as date)                 then 'A vencer'
         when cast(:{p} as date) - t.data_vencimento <= 30           then '1-30d'
         when cast(:{p} as date) - t.data_vencimento <= 60           then '31-60d'
         when cast(:{p} as date) - t.data_vencimento <= 90           then '61-90d'
         when cast(:{p} as date) - t.data_vencimento <= 180          then '91-180d'
         else '180+d' end
"""


def _ordenar_faixas(df: pd.DataFrame, coluna: str = "faixa") -> pd.DataFrame:
    ordem = {f: i for i, f in enumerate(config.FAIXAS_AGING)}
    df = df.copy()
    df["ordem"] = df[coluna].map(ordem)
    return df.sort_values("ordem").drop(columns=["ordem"]).reset_index(drop=True)


def inadimplencia_ponto_no_tempo(
    filtros: Filtros, data_ref: date | None = None
) -> pd.DataFrame:
    """Inadimplencia > 30 dias numa data de referencia qualquer. Uma linha.

    Colunas: ``data_ref``, ``valor_vencido_30d``, ``qtd_titulos_vencidos``,
    ``faturamento_bruto_12m``, ``inadimplencia_pct``, ``janela_ini``,
    ``janela_fim``, ``janela_completa``.

    Definicao: ver o docstring do modulo. Vale para **qualquer** data entre
    2024-01-01 e 2026-08-31.

    Filtros ignorados: ``competencia_ini`` / ``competencia_fim``. O numerador e a
    carteira inteira na data (um titulo de 2024 ainda vencido conta na foto de
    2026) e o denominador e a janela movel fixa de 12 meses. Recortes de cliente,
    segmento, rating, porte, UF, tipo de receita e tipo de contrato **sao**
    aplicados, aos dois lados da fracao.
    """
    ref = data_ref or filtros.ref
    cond, params = condicoes_titulos(filtros, com_periodo=False, com_cancelados=True)
    params["ref"] = ref
    sql = f"""
    with base as (
        select t.id_titulo, t.valor_bruto, t.competencia, t.data_vencimento,
               t.data_pagamento, t.data_cancelamento
        {_DE}
        where 1=1{cond}
    ),
    numerador as (
        select coalesce(sum(t.valor_bruto), 0)::float8 as valor_vencido_30d,
               count(*) as qtd_titulos_vencidos
        from base t
        where t.data_vencimento <= cast(:ref as date) - {config.DIAS_CARENCIA_INADIMPLENCIA}
          and {clausula_nao_pago_em('t')}
          and {clausula_valida_em('t')}
    ),
    denominador as (
        select coalesce(sum(t.valor_bruto), 0)::float8 as faturamento_bruto_12m,
               min(t.competencia) as janela_ini,
               max(t.competencia) as janela_fim
        from base t
        where t.competencia > (date_trunc('month', cast(:ref as date))
                               - interval '{config.MESES_JANELA_INADIMPLENCIA} months')::date
          and t.competencia <= date_trunc('month', cast(:ref as date))::date
          and {clausula_valida_em('t')}
    )
    select cast(:ref as date) as data_ref, n.*, d.*,
           (100.0 * n.valor_vencido_30d / nullif(d.faturamento_bruto_12m, 0))::float8
               as inadimplencia_pct
    from numerador n cross join denominador d
    """
    df = db.consultar(sql, params, ttl=config.TTL_PESADO)
    limite = pd.Timestamp(config.COMPETENCIA_MIN) + pd.DateOffset(months=11)
    df["janela_completa"] = pd.to_datetime(df["data_ref"]) >= limite
    return df


def aging_carteira(filtros: Filtros, data_ref: date | None = None) -> pd.DataFrame:
    """Aging da carteira em aberto numa data de referencia qualquer.

    Colunas: ``faixa`` (A vencer · 1-30d · 31-60d · 61-90d · 91-180d · 180+d),
    ``valor_bruto``, ``qtd_titulos``, ``participacao_pct``.

    Definicao: titulos **nao pagos**, **nao cancelados** e **nao baixados** na
    data de referencia; faixa pelos dias corridos entre ``data_vencimento`` e a
    data de referencia. Reproduz o publicado em 2026-08-31: a vencer 4,47 mi ·
    1-30d 0,76 · 31-60d 0,44 · 61-90d 0,40 · 91-180d 0,77 · 180+ 0,82 mi.

    Sutileza registrada: 4 titulos ja marcados ``Baixado`` na foto de extracao tem
    ``data_baixa`` posterior a 2026-08-31 (a baixa e lancada em venc + 370..430
    dias). Um filtro puramente point-in-time os manteria e o balde 180+ daria
    1,00 mi em vez de 0,82 mi. Ver :func:`frotas.filtros.clausula_nao_baixado_em`.

    Filtros ignorados: ``competencia_ini`` / ``competencia_fim`` -- e uma foto da
    carteira inteira, nao um recorte de competencia.
    """
    ref = data_ref or filtros.ref
    cond, params = condicoes_titulos(filtros, com_periodo=False, com_cancelados=True)
    params["ref"] = ref
    params["data_extracao"] = config.DATA_EXTRACAO
    sql = f"""
    select {_FAIXA.format(p='ref').strip()} as faixa,
           sum(t.valor_bruto)::float8 as valor_bruto,
           count(*) as qtd_titulos
    {_DE}
    where {clausula_nao_pago_em('t')}
      and {clausula_valida_em('t')}
      and {clausula_nao_baixado_em('t')}
      {cond}
    group by 1
    """
    df = db.consultar(sql, params, ttl=config.TTL_PESADO)
    total = df["valor_bruto"].sum()
    df["participacao_pct"] = 100.0 * df["valor_bruto"] / total if total else 0.0
    return _ordenar_faixas(df)


def aging_por_cliente(
    filtros: Filtros, data_ref: date | None = None, limite: int | None = None
) -> pd.DataFrame:
    """Aging aberto por cliente, em formato largo (uma coluna por faixa).

    Colunas: ``id_cliente``, ``nome_cliente``, ``segmento``, ``porte``,
    ``rating_credito``, ``limite_credito``, uma coluna por faixa de
    :data:`frotas.config.FAIXAS_AGING`, ``carteira_total``,
    ``vencido_30d_mais``, ``pct_vencido_30d``, ``uso_limite_pct``.

    Mesmas regras de :func:`aging_carteira`.
    """
    ref = data_ref or filtros.ref
    cond, params = condicoes_titulos(filtros, com_periodo=False, com_cancelados=True)
    params["ref"] = ref
    params["data_extracao"] = config.DATA_EXTRACAO
    sql = f"""
    select cl.id_cliente, cl.nome_cliente, cl.segmento, cl.porte, cl.rating_credito,
           max(cl.limite_credito)::float8 as limite_credito,
           {_FAIXA.format(p='ref').strip()} as faixa,
           sum(t.valor_bruto)::float8 as valor_bruto
    {_DE}
    where {clausula_nao_pago_em('t')}
      and {clausula_valida_em('t')}
      and {clausula_nao_baixado_em('t')}
      {cond}
    group by 1, 2, 3, 4, 5, 7
    """
    longo = db.consultar(sql, params, ttl=config.TTL_PESADO)
    if longo.empty:
        return longo
    chaves = ["id_cliente", "nome_cliente", "segmento", "porte", "rating_credito", "limite_credito"]
    largo = (
        longo.pivot_table(index=chaves, columns="faixa", values="valor_bruto", aggfunc="sum")
        .reindex(columns=list(config.FAIXAS_AGING))
        .fillna(0.0)
        .reset_index()
    )
    largo.columns.name = None
    vencidas = [f for f in config.FAIXAS_AGING if f not in ("A vencer", "1-30d")]
    largo["carteira_total"] = largo[list(config.FAIXAS_AGING)].sum(axis=1)
    largo["vencido_30d_mais"] = largo[vencidas].sum(axis=1)
    largo["pct_vencido_30d"] = (
        100.0 * largo["vencido_30d_mais"] / largo["carteira_total"].replace(0, pd.NA)
    )
    largo["uso_limite_pct"] = (
        100.0 * largo["carteira_total"] / largo["limite_credito"].replace(0, pd.NA)
    )
    largo = largo.sort_values("vencido_30d_mais", ascending=False).reset_index(drop=True)
    return largo.head(limite) if limite else largo


def risco_por_rating(filtros: Filtros, data_ref: date | None = None) -> pd.DataFrame:
    """Exposicao e inadimplencia por rating de credito.

    Colunas: ``rating_credito``, ``qtd_clientes``, ``carteira_total``,
    ``vencido_30d_mais``, ``pct_vencido_30d``, ``faturamento_bruto_12m``,
    ``inadimplencia_pct``, ``limite_credito_total``.

    ``inadimplencia_pct`` usa a definicao canonica do modulo (vencido > 30d sobre
    faturamento dos 12 meses de competencia), calculada **dentro** de cada rating.
    """
    return _risco_por(filtros, "cl.rating_credito", "rating_credito", data_ref)


def risco_por_segmento(filtros: Filtros, data_ref: date | None = None) -> pd.DataFrame:
    """Mesma leitura de :func:`risco_por_rating`, quebrada por segmento de cliente.

    Colunas: ``segmento`` + as mesmas medidas. E aqui que aparece o estresse da
    Construcao Civil no 2o semestre de 2025.
    """
    return _risco_por(filtros, "cl.segmento", "segmento", data_ref)


def _risco_por(
    filtros: Filtros, expressao: str, rotulo: str, data_ref: date | None
) -> pd.DataFrame:
    ref = data_ref or filtros.ref
    cond, params = condicoes_titulos(filtros, com_periodo=False, com_cancelados=True)
    params["ref"] = ref
    params["data_extracao"] = config.DATA_EXTRACAO
    sql = f"""
    with base as (
        select {expressao} as chave, cl.id_cliente, cl.limite_credito,
               t.valor_bruto, t.competencia, t.data_vencimento,
               t.data_pagamento, t.data_cancelamento, t.data_baixa
        {_DE}
        where 1=1{cond}
    )
    select b.chave as {rotulo},
           count(distinct b.id_cliente) as qtd_clientes,
           coalesce(sum(b.valor_bruto) filter (
               where (b.data_pagamento is null or b.data_pagamento > cast(:ref as date))
                 and (b.data_cancelamento is null or b.data_cancelamento > cast(:ref as date))
                 and (b.data_baixa is null or (b.data_baixa > cast(:ref as date)
                      and cast(:ref as date) < cast(:data_extracao as date)))), 0)::float8
               as carteira_total,
           coalesce(sum(b.valor_bruto) filter (
               where b.data_vencimento <= cast(:ref as date) - {config.DIAS_CARENCIA_INADIMPLENCIA}
                 and (b.data_pagamento is null or b.data_pagamento > cast(:ref as date))
                 and (b.data_cancelamento is null or b.data_cancelamento > cast(:ref as date))), 0)::float8
               as vencido_30d_mais,
           coalesce(sum(b.valor_bruto) filter (
               where b.competencia > (date_trunc('month', cast(:ref as date))
                                      - interval '{config.MESES_JANELA_INADIMPLENCIA} months')::date
                 and b.competencia <= date_trunc('month', cast(:ref as date))::date
                 and (b.data_cancelamento is null or b.data_cancelamento > cast(:ref as date))), 0)::float8
               as faturamento_bruto_12m
    from base b
    group by 1
    order by 1
    """
    df = db.consultar(sql, params, ttl=config.TTL_PESADO)
    df["inadimplencia_pct"] = (
        100.0 * df["vencido_30d_mais"] / df["faturamento_bruto_12m"].replace(0, pd.NA)
    )
    df["pct_vencido_30d"] = (
        100.0 * df["vencido_30d_mais"] / df["carteira_total"].replace(0, pd.NA)
    )
    return df


def risco_por_cliente(
    filtros: Filtros, data_ref: date | None = None, limite: int | None = 20
) -> pd.DataFrame:
    """Ranking de clientes por valor vencido ha mais de 30 dias.

    Colunas: ``id_cliente``, ``nome_cliente``, ``segmento``, ``porte``,
    ``rating_credito``, ``limite_credito``, ``carteira_total``,
    ``vencido_30d_mais``, ``faturamento_bruto_12m``, ``inadimplencia_pct``,
    ``pct_vencido_30d``, ``uso_limite_pct``.

    E aqui que o cliente Grande que para de pagar em set/2025 aparece no topo.
    """
    ref = data_ref or filtros.ref
    cond, params = condicoes_titulos(filtros, com_periodo=False, com_cancelados=True)
    params["ref"] = ref
    params["data_extracao"] = config.DATA_EXTRACAO
    sql = f"""
    select cl.id_cliente, cl.nome_cliente, cl.segmento, cl.porte, cl.rating_credito,
           max(cl.limite_credito)::float8 as limite_credito,
           coalesce(sum(t.valor_bruto) filter (
               where {clausula_nao_pago_em('t')} and {clausula_valida_em('t')}
                 and {clausula_nao_baixado_em('t')}), 0)::float8 as carteira_total,
           coalesce(sum(t.valor_bruto) filter (
               where t.data_vencimento <= cast(:ref as date) - {config.DIAS_CARENCIA_INADIMPLENCIA}
                 and {clausula_nao_pago_em('t')} and {clausula_valida_em('t')}), 0)::float8
               as vencido_30d_mais,
           coalesce(sum(t.valor_bruto) filter (
               where t.competencia > (date_trunc('month', cast(:ref as date))
                                      - interval '{config.MESES_JANELA_INADIMPLENCIA} months')::date
                 and t.competencia <= date_trunc('month', cast(:ref as date))::date
                 and {clausula_valida_em('t')}), 0)::float8 as faturamento_bruto_12m
    {_DE}
    where 1=1{cond}
    group by 1, 2, 3, 4, 5
    order by vencido_30d_mais desc
    """
    df = db.consultar(sql, params, ttl=config.TTL_PESADO)
    df["inadimplencia_pct"] = (
        100.0 * df["vencido_30d_mais"] / df["faturamento_bruto_12m"].replace(0, pd.NA)
    )
    df["pct_vencido_30d"] = (
        100.0 * df["vencido_30d_mais"] / df["carteira_total"].replace(0, pd.NA)
    )
    df["uso_limite_pct"] = (
        100.0 * df["carteira_total"] / df["limite_credito"].replace(0, pd.NA)
    )
    return df.head(limite) if limite else df


def titulos_do_cliente(
    filtros: Filtros, id_cliente: str, data_ref: date | None = None
) -> pd.DataFrame:
    """Linhas de ``titulos_receber`` de um cliente -- o drill ate o titulo.

    E a **unica** funcao da camada semantica que devolve grao de titulo. Todas as
    outras agregam.

    Colunas: ``id_titulo``, ``id_contrato``, ``tipo_receita``, ``descricao``,
    ``competencia``, ``ano_mes``, ``data_emissao``, ``data_vencimento``,
    ``valor_bruto``, ``valor_liquido``, ``data_pagamento``, ``valor_pago``,
    ``valor_juros_multa``, ``dias_atraso``, ``faixa``, ``status_calculado``,
    ``status_titulo_gravado``, ``forma_pagamento``, ``motivo_cancelamento``,
    ``motivo_baixa``.

    Armadilha tratada (2): ``status_calculado`` e **recalculado** na data de
    referencia a partir das datas, nunca lido de ``status_titulo`` (que e a foto
    de 2026-08-31). Valores: ``Pago``, ``Pago com atraso``, ``Cancelado``,
    ``Baixado``, ``Vencido``, ``A vencer``. Do mesmo jeito, ``dias_atraso`` e
    ``:ref - data_vencimento`` para quem estava em aberto na ``:ref``, e
    ``dias_atraso_pagamento`` para quem ja tinha pago -- nulo para quem nao
    estava atrasado.

    O filtro de competencia **e** aplicado aqui (diferente das metricas de foto):
    o gerente de cobranca quer ver a linha do tempo do cliente no periodo da tela.
    Passe ``Filtros(competencia_ini=None, competencia_fim=None)`` para o historico
    completo.
    """
    cond, params = condicoes_titulos(filtros, com_cancelados=True)
    ref = data_ref or filtros.ref
    params["ref"] = ref
    params["data_extracao"] = config.DATA_EXTRACAO
    params["id_cliente_drill"] = id_cliente
    sql = f"""
    select t.id_titulo, t.id_contrato, t.tipo_receita, t.descricao,
           t.competencia, to_char(t.competencia, 'YYYY-MM') as ano_mes,
           t.data_emissao, t.data_vencimento,
           t.valor_bruto::float8 as valor_bruto,
           t.valor_liquido::float8 as valor_liquido,
           t.data_pagamento, t.valor_pago::float8 as valor_pago,
           coalesce(t.valor_juros_multa, 0)::float8 as valor_juros_multa,
           case
             when t.data_cancelamento is not null and t.data_cancelamento <= cast(:ref as date)
               then null
             when t.data_pagamento is not null and t.data_pagamento <= cast(:ref as date)
               then nullif(greatest(coalesce(t.dias_atraso_pagamento, 0), 0), 0)
             when t.data_vencimento < cast(:ref as date)
               then (cast(:ref as date) - t.data_vencimento)
             else null
           end as dias_atraso,
           case when t.data_cancelamento is not null and t.data_cancelamento <= cast(:ref as date)
                     then 'Cancelado'
                when t.data_baixa is not null
                     and (t.data_baixa <= cast(:ref as date)
                          or cast(:ref as date) >= cast(:data_extracao as date))
                     then 'Baixado'
                when t.data_pagamento is not null and t.data_pagamento <= cast(:ref as date)
                     then case when coalesce(t.dias_atraso_pagamento, 0) > 0
                               then 'Pago com atraso' else 'Pago' end
                when t.data_vencimento < cast(:ref as date) then 'Vencido'
                else 'A vencer' end as status_calculado,
           case when t.data_cancelamento is not null and t.data_cancelamento <= cast(:ref as date)
                     then 'Cancelado'
                when t.data_pagamento is not null and t.data_pagamento <= cast(:ref as date)
                     then 'Pago'
                when t.data_vencimento > cast(:ref as date)                then 'A vencer'
                when cast(:ref as date) - t.data_vencimento <= 30          then '1-30d'
                when cast(:ref as date) - t.data_vencimento <= 60          then '31-60d'
                when cast(:ref as date) - t.data_vencimento <= 90          then '61-90d'
                when cast(:ref as date) - t.data_vencimento <= 180         then '91-180d'
                else '180+d' end as faixa,
           t.status_titulo as status_titulo_gravado,
           t.forma_pagamento, t.motivo_cancelamento, t.motivo_baixa
    {_DE}
    where t.id_cliente = :id_cliente_drill{cond}
    order by t.data_vencimento, t.id_titulo
    """
    return db.consultar(sql, params, ttl=config.TTL_FATOS)


def cobertura_de_caixa(filtros: Filtros, data_ref: date | None = None) -> pd.DataFrame:
    """Cobertura de caixa dos 12 meses moveis: caixa recebido / faturamento valido.

    Uma linha. Colunas: ``data_ref``, ``janela_ini``, ``janela_fim``,
    ``recebimento_12m`` (o caixa de verdade, **com** juros e multa),
    ``recebimento_sem_juros_12m`` (o numerador da razao),
    ``faturamento_valido_12m``, ``cobertura_pct``.

    Definicao: a razao usa ``sum(valor_pago - valor_juros_multa)`` com
    ``data_pagamento`` nos 12 meses que terminam na data de referencia;
    faturamento valido = ``sum(valor_bruto)`` das 12 competencias que terminam no
    mes da referencia, com filtro point-in-time de cancelamento. Em ago/26:
    **92,5%** (32,490 / 35,120 mi), **abaixo** do piso de 93% da `Revisao 2026`.

    Os dois recebimentos convivem de proposito: o caixa que entrou no banco tem
    juros e multa e e ele que o cartao de "Recebimento em 12 meses" mostra; a
    razao tira os juros, porque o denominador nao os tem.

    Juros e multa ficam **fora** do numerador de proposito. Eles nao existem no
    denominador nem na meta (o plano aplica a taxa sobre o faturado puro), entao
    inclui-los somava 1,3 p.p. -- e fazia cliente que atrasa e paga com juros
    *melhorar* o indicador. Com eles o numero publicado era 93,8%, o que mantinha
    o alerta em ambar e escondia que o piso ja tinha sido rompido.

    Nao e uma medida de eficiencia de cobranca, e por isso nao se chama assim: o
    numerador e o denominador nao sao a mesma populacao. O caixa do mes reflete o
    faturamento de m-1 a m-3, entao empresa crescendo derruba a razao mesmo com
    cobranca perfeita, e queda de faturamento a levanta sozinha. A leitura honesta
    e "o caixa acompanha o faturado?". Cobranca de verdade se mede por safra de
    competencia, que esta fora do escopo dos cinco eixos.
    """
    ref = data_ref or filtros.ref
    cond, params = condicoes_titulos(filtros, com_periodo=False, com_cancelados=True)
    params["ref"] = ref
    sql = f"""
    select cast(:ref as date) as data_ref,
           (date_trunc('month', cast(:ref as date))
            - interval '{config.MESES_JANELA_INADIMPLENCIA - 1} months')::date as janela_ini,
           date_trunc('month', cast(:ref as date))::date as janela_fim,
           coalesce(sum(t.valor_pago) filter (
               where t.data_pagamento > (cast(:ref as date) - interval '1 year')::date
                 and t.data_pagamento <= cast(:ref as date)), 0)::float8 as recebimento_12m,
           coalesce(sum(t.valor_pago - coalesce(t.valor_juros_multa, 0)) filter (
               where t.data_pagamento > (cast(:ref as date) - interval '1 year')::date
                 and t.data_pagamento <= cast(:ref as date)), 0)::float8
               as recebimento_sem_juros_12m,
           coalesce(sum(t.valor_bruto) filter (
               where t.competencia > (date_trunc('month', cast(:ref as date))
                                      - interval '{config.MESES_JANELA_INADIMPLENCIA} months')::date
                 and t.competencia <= date_trunc('month', cast(:ref as date))::date
                 and {clausula_valida_em('t')}), 0)::float8 as faturamento_valido_12m
    {_DE}
    where 1=1{cond}
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    df["cobertura_pct"] = (
        100.0 * df["recebimento_sem_juros_12m"] / df["faturamento_valido_12m"].replace(0, pd.NA)
    )
    return df


def titulos_em_risco_de_baixa(
    filtros: Filtros, data_ref: date | None = None, dias_limite: int = 300
) -> pd.DataFrame:
    """Titulos vencidos ha mais de N dias, nao pagos e nao cancelados na ``:ref``.

    Colunas: ``id_titulo``, ``id_cliente``, ``nome_cliente``, ``segmento``,
    ``rating_credito``, ``competencia``, ``data_vencimento``, ``dias_vencido``,
    ``valor_bruto``.

    Alerta A12: a regra de negocio baixa o titulo aos **365 dias** de vencimento
    (viram ``Baixado``, motivo decomposto). Estes sao os que ainda dao para
    cobrar -- R$ 664 mil ja viraram Perda Cobravel no historico.

    Filtros ignorados: competencia -- e uma foto da carteira, como o aging.
    """
    ref = data_ref or filtros.ref
    cond, params = condicoes_titulos(filtros, com_periodo=False, com_cancelados=True)
    params["ref"] = ref
    params["dias_limite"] = int(dias_limite)
    sql = f"""
    select t.id_titulo, t.id_cliente, cl.nome_cliente, cl.segmento, cl.rating_credito,
           t.competencia, t.data_vencimento,
           (cast(:ref as date) - t.data_vencimento) as dias_vencido,
           t.valor_bruto::float8 as valor_bruto
    {_DE}
    where t.data_vencimento <= cast(:ref as date) - :dias_limite
      and {clausula_nao_pago_em('t')}
      and {clausula_valida_em('t')}
      {cond}
    order by t.data_vencimento
    """
    return db.consultar(sql, params, ttl=config.TTL_PESADO)


def titulos_com_baixa_futura(
    filtros: Filtros, data_ref: date | None = None
) -> pd.DataFrame:
    """Titulos cuja ``data_baixa`` e posterior a data de referencia -- defeito de foto.

    Colunas: ``id_titulo``, ``id_cliente``, ``nome_cliente``, ``data_vencimento``,
    ``data_baixa``, ``motivo_baixa``, ``valor_bruto``.

    Alerta A18. Sao **4 titulos, R$ 182 mil**, com baixa lancada entre 2026-09-15 e
    2026-10-19 -- depois da extracao. Consequencia pratica: ``data_baixa is null``
    **nao** e proxy de "vivo na foto". O aging os exclui (e assim reproduz os
    0,82 mi da faixa 180+); a inadimplencia nao os exclui. As duas leituras estao
    certas e sao diferentes de proposito -- rotular na tela.
    """
    ref = data_ref or filtros.ref
    cond, params = condicoes_titulos(filtros, com_periodo=False, com_cancelados=True)
    params["ref"] = ref
    sql = f"""
    select t.id_titulo, t.id_cliente, cl.nome_cliente, t.data_vencimento,
           t.data_baixa, t.motivo_baixa, t.valor_bruto::float8 as valor_bruto
    {_DE}
    where t.data_baixa > cast(:ref as date){cond}
    order by t.data_baixa
    """
    return db.consultar(sql, params, ttl=config.TTL_FATOS)
