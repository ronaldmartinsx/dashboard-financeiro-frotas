"""Realizado x meta (orcamento), com as regras de consolidacao da tabela ``metas``.

Escopo do modulo (reduzido): **cinco** das seis metricas orcadas. ``Margem
Operacional`` saiu do projeto por completo -- inclusive como linha da tabela de
metas. Ela continua no banco (e ``versoes_orcamento`` a mostra, porque le a
tabela crua), mas nenhuma funcao deste modulo a consolida ou a compara.

Tres regras mandam aqui, e as tres sao armadilhas do briefing:

* **Armadilha 3 -- ``eh_versao_vigente``.** 2026 tem duas versoes de orcamento
  (``Orcamento Original``, nao vigente, e ``Revisao 2026``, vigente). Somar as
  duas dobra o ano. **Toda** consulta deste modulo filtra ``eh_versao_vigente``.
  :func:`versoes_orcamento` existe justamente para mostrar as duas lado a lado
  sem misturar.
* **Armadilha 4 -- metas percentuais nao se somam.** ``tipo_agregacao`` manda:
  ``Soma`` (as quatro metricas em BRL) e ``Fim de Periodo`` (Inadimplencia > 30d,
  que vale o valor do ultimo mes do periodo, nunca a media dos meses).
* **Armadilha 7 -- 2026 e parcial.** Metricas ``Soma`` sao comparadas contra a
  soma das metas **dos mesmos meses realizados**, nunca contra o ano cheio
  (jan-ago/2026 = 23,92 mi de meta, nao 35,82 mi).

**Base de comparacao.** Para ``Soma`` a base e o periodo alinhado. Para
``Fim de Periodo`` a base publicada e a **meta anual** -- e assim que o dicionario
chega a +2,02 p.p. de inadimplencia em 2026: inadimplencia de ago/26 (10,02%)
contra o alvo de dez (8,00%). O DataFrame devolve as duas leituras
(``meta_alinhada`` e ``meta_anual``) e diz em ``base_comparacao`` qual foi usada
na variacao.

Filtros ignorados: praticamente todos. A tabela ``metas`` so tem os niveis
Empresa e Segmento -- nao existe meta por cliente, rating, categoria de veiculo
ou tipo de receita. Filtrar o realizado sem filtrar a meta inventaria variacao.
Use ``nivel``/``chave`` para recortar; ``Custo Operacional`` e
``Inadimplencia > 30d`` so existem no nivel Empresa (armadilha 6).
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from frotas import config, db

Nivel = Literal["Empresa", "Segmento"]

#: Metricas orcadas dentro do escopo do app e como o realizado de cada uma e
#: calculado. ``Margem Operacional`` existe na tabela ``metas``, mas **nao** neste
#: projeto: foi retirada do escopo e nao aparece na tabela de metas do app.
TIPOS_META: tuple[str, ...] = (
    "Faturamento",
    "Receita Liquida",
    "Recebimento (Caixa)",
    "Custo Operacional",
    "Inadimplencia > 30d",
)

#: Metricas que so existem no nivel Empresa (armadilha 6: ocioso sem segmento).
SO_EMPRESA: frozenset[str] = frozenset({"Custo Operacional", "Inadimplencia > 30d"})


def _cond_segmento(nivel: Nivel, chave: str, alias: str = "cl") -> tuple[str, dict]:
    if nivel == "Segmento":
        return f" and {alias}.segmento = :chave", {"chave": chave}
    return "", {}


def _realizado_titulos(
    coluna: str, ano: int | None, nivel: Nivel, chave: str
) -> pd.DataFrame:
    cond, params = _cond_segmento(nivel, chave)
    if ano is not None:
        cond += " and extract(year from t.competencia) = :ano"
        params["ano"] = ano
    sql = f"""
    select to_char(t.competencia, 'YYYY-MM') as ano_mes,
           sum(t.{coluna})::float8 as realizado
    from public.titulos_receber t
    join public.clientes cl on cl.id_cliente = t.id_cliente
    where 1=1{cond}
    group by 1
    order by 1
    """
    return db.consultar(sql, params, ttl=config.TTL_FATOS)


def _realizado_recebimento(ano: int | None, nivel: Nivel, chave: str) -> pd.DataFrame:
    """Caixa realizado: soma de ``valor_pago`` pelo **mes do pagamento**.

    Inclui ``valor_juros_multa`` (esta dentro de ``valor_pago``) -- e o que
    reproduz -4,7% (2024), -2,9% (2025) e +3,6% (2026, 8m) contra a meta.
    """
    cond, params = _cond_segmento(nivel, chave)
    if ano is not None:
        cond += " and extract(year from t.data_pagamento) = :ano"
        params["ano"] = ano
    sql = f"""
    select to_char(t.data_pagamento, 'YYYY-MM') as ano_mes,
           sum(t.valor_pago)::float8 as realizado
    from public.titulos_receber t
    join public.clientes cl on cl.id_cliente = t.id_cliente
    where t.data_pagamento is not null{cond}
    group by 1
    order by 1
    """
    return db.consultar(sql, params, ttl=config.TTL_FATOS)


def _realizado_custo(ano: int | None) -> pd.DataFrame:
    cond, params = "", {}
    if ano is not None:
        cond = " and extract(year from cs.competencia) = :ano"
        params["ano"] = ano
    sql = f"""
    select to_char(cs.competencia, 'YYYY-MM') as ano_mes,
           sum(cs.valor)::float8 as realizado
    from public.custos cs
    where 1=1{cond}
    group by 1
    order by 1
    """
    return db.consultar(sql, params, ttl=config.TTL_FATOS)


def _realizado_inadimplencia(ano: int | None) -> pd.DataFrame:
    """Inadimplencia > 30d point-in-time no ultimo dia de cada mes."""
    params: dict = {
        "serie_ini": config.COMPETENCIA_MIN,
        "serie_fim": config.COMPETENCIA_MAX,
    }
    sql = f"""
    with refs as (
        select (generate_series(cast(:serie_ini as date), cast(:serie_fim as date),
                                interval '1 month') + interval '1 month - 1 day')::date as data_ref
    )
    select to_char(r.data_ref, 'YYYY-MM') as ano_mes,
           (100.0 *
             (select coalesce(sum(t.valor_bruto), 0) from public.titulos_receber t
               where t.data_vencimento <= r.data_ref - {config.DIAS_CARENCIA_INADIMPLENCIA}
                 and (t.data_pagamento is null or t.data_pagamento > r.data_ref)
                 and (t.data_cancelamento is null or t.data_cancelamento > r.data_ref))
             / nullif(
             (select coalesce(sum(t.valor_bruto), 0) from public.titulos_receber t
               where t.competencia > (date_trunc('month', r.data_ref)
                                      - interval '{config.MESES_JANELA_INADIMPLENCIA} months')::date
                 and t.competencia <= date_trunc('month', r.data_ref)::date
                 and (t.data_cancelamento is null or t.data_cancelamento > r.data_ref)), 0)
           )::float8 as realizado
    from refs r
    order by 1
    """
    df = db.consultar(sql, params, ttl=config.TTL_PESADO)
    if ano is not None:
        df = df[df["ano_mes"].str.startswith(f"{ano}-")].reset_index(drop=True)
    return df


def realizado_mensal(
    tipo_meta: str, ano: int | None = None, nivel: Nivel = "Empresa", chave: str = "TOTAL"
) -> pd.DataFrame:
    """Serie mensal realizada de uma das 5 metricas orcadas em escopo.

    Colunas: ``ano_mes``, ``realizado``.

    Definicoes: Faturamento = ``sum(valor_bruto)`` por competencia; Receita
    Liquida = ``sum(valor_liquido)`` por competencia (as duas incluindo
    cancelados); Recebimento (Caixa) = ``sum(valor_pago)`` pelo mes do pagamento;
    Custo Operacional = ``sum(custos.valor)`` por competencia (inclui ocioso);
    Inadimplencia > 30d = metrica point-in-time no ultimo dia do mes.
    """
    if tipo_meta not in TIPOS_META:
        raise ValueError(f"tipo_meta invalido: {tipo_meta!r}. Use um de {list(TIPOS_META)}.")
    if tipo_meta in SO_EMPRESA and nivel != "Empresa":
        raise ValueError(
            f"'{tipo_meta}' so existe no nivel Empresa: custo de veiculo ocioso "
            "(custos.id_contrato IS NULL) nao tem segmento a que ser atribuido."
        )
    if tipo_meta == "Faturamento":
        return _realizado_titulos("valor_bruto", ano, nivel, chave)
    if tipo_meta == "Receita Liquida":
        return _realizado_titulos("valor_liquido", ano, nivel, chave)
    if tipo_meta == "Recebimento (Caixa)":
        return _realizado_recebimento(ano, nivel, chave)
    if tipo_meta == "Custo Operacional":
        return _realizado_custo(ano)
    return _realizado_inadimplencia(ano)


def metas_do_ano(ano: int, nivel: Nivel = "Empresa", chave: str = "TOTAL") -> pd.DataFrame:
    """Todas as metas vigentes de um ano/recorte em **uma** ida ao banco.

    Colunas: ``tipo_meta``, ``granularidade``, ``ano_mes``, ``trimestre``,
    ``meta``, ``unidade``, ``tipo_agregacao``, ``versao_meta``.

    Filtra ``eh_versao_vigente`` (armadilha 3). :func:`metas_mensais` e
    :func:`meta_anual` recortam este DataFrame em memoria -- sao 60 linhas por
    ano, nao vale um round-trip cada.
    """
    sql = """
    select m.tipo_meta, m.granularidade, m.ano_mes, m.trimestre,
           m.valor_meta::float8 as meta, m.unidade, m.tipo_agregacao, m.versao_meta
    from public.metas m
    where m.eh_versao_vigente
      and m.nivel_analise = :nivel
      and m.chave_nivel = :chave
      and m.ano = :ano
    order by m.tipo_meta, m.granularidade, m.ano_mes
    """
    return db.consultar(
        sql,
        {"nivel": nivel, "chave": chave, "ano": ano},
        ttl=config.TTL_FATOS,
    )


def metas_mensais(
    tipo_meta: str, ano: int, nivel: Nivel = "Empresa", chave: str = "TOTAL"
) -> pd.DataFrame:
    """Metas mensais **da versao vigente** (armadilha 3).

    Colunas: ``ano_mes``, ``meta``, ``unidade``, ``tipo_agregacao``,
    ``versao_meta``.
    """
    todas = metas_do_ano(ano, nivel, chave)
    df = todas[(todas["tipo_meta"] == tipo_meta) & (todas["granularidade"] == "Mensal")]
    return df[["ano_mes", "meta", "unidade", "tipo_agregacao", "versao_meta"]].sort_values(
        "ano_mes"
    ).reset_index(drop=True)


def meta_anual(
    tipo_meta: str, ano: int, nivel: Nivel = "Empresa", chave: str = "TOTAL"
) -> pd.DataFrame:
    """Linha anual da meta vigente. Colunas: ``meta``, ``unidade``, ``tipo_agregacao``, ``versao_meta``."""
    todas = metas_do_ano(ano, nivel, chave)
    df = todas[(todas["tipo_meta"] == tipo_meta) & (todas["granularidade"] == "Anual")]
    return df[["meta", "unidade", "tipo_agregacao", "versao_meta"]].reset_index(drop=True)


def _consolidar(valores: pd.DataFrame, coluna: str, tipo_agregacao: str) -> float:
    """Aplica ``tipo_agregacao`` a uma serie mensal. Nunca soma percentual.

    Sobraram duas agregacoes no escopo: ``Fim de Periodo`` (Inadimplencia > 30d,
    que vale o valor do ultimo mes) e ``Soma`` (as quatro metricas em BRL).
    ``Media Ponderada`` era exclusiva da Margem Operacional e saiu com ela.
    """
    serie = valores[coluna].astype(float)
    if serie.empty:
        return float("nan")
    if tipo_agregacao.startswith("Fim de Periodo"):
        return float(serie.iloc[-1])
    return float(serie.sum())


def serie_mensal(
    tipo_meta: str, ano: int, nivel: Nivel = "Empresa", chave: str = "TOTAL"
) -> pd.DataFrame:
    """Realizado x meta mes a mes, para o grafico de acompanhamento.

    Colunas: ``ano_mes``, ``realizado``, ``meta``, ``variacao_abs``,
    ``variacao_pct`` (so para metricas BRL; para % use ``variacao_abs``, que ja
    esta em pontos percentuais), ``unidade``, ``tipo_agregacao``, ``versao_meta``.

    Meses sem realizado (o futuro de 2026) vem com ``realizado`` nulo, nunca zero.
    """
    real = realizado_mensal(tipo_meta, ano, nivel, chave)[["ano_mes", "realizado"]]
    alvo = metas_mensais(tipo_meta, ano, nivel, chave)
    df = alvo.merge(real, on="ano_mes", how="left")
    df["variacao_abs"] = df["realizado"] - df["meta"]
    percentual = (df["unidade"] == "%").any()
    df["variacao_pct"] = (
        pd.NA if percentual else 100.0 * df["variacao_abs"] / df["meta"].replace(0, pd.NA)
    )
    return df[
        ["ano_mes", "realizado", "meta", "variacao_abs", "variacao_pct",
         "unidade", "tipo_agregacao", "versao_meta"]
    ]


def comparativo_anual(
    ano: int,
    nivel: Nivel = "Empresa",
    chave: str = "TOTAL",
    tipos: tuple[str, ...] | None = None,
    base: Literal["alinhada", "anual"] = "alinhada",
) -> pd.DataFrame:
    """Realizado x meta consolidado do ano -- a tabela de variacao do app.

    Colunas: ``tipo_meta``, ``unidade``, ``tipo_agregacao``, ``versao_meta``,
    ``meses_realizados``, ``periodo_realizado``, ``eh_parcial``, ``realizado``,
    ``meta_alinhada`` (mesmos meses do realizado), ``meta_anual`` (ano cheio),
    ``meta_comparavel``, ``base_comparacao``, ``variacao_abs``, ``variacao_pct``.

    Regras aplicadas:

    * ``Soma``: realizado = soma dos meses realizados; ``meta_alinhada`` = soma
      das metas dos mesmos meses. Para 2026 isso da **+2,9%** de faturamento
      (24,62 mi contra 23,92 mi de meta jan-ago); contra o ano cheio daria -31%,
      que e mentira (armadilha 7).
    * ``Fim de Periodo`` (Inadimplencia): realizado = valor do ultimo mes
      realizado; ``meta_alinhada`` = meta **desse mesmo mes**.

    ``Margem Operacional`` **nao aparece** nesta tabela: saiu do escopo do
    projeto. Pedi-la em ``tipos`` levanta ``ValueError``, como qualquer outro
    tipo fora de :data:`TIPOS_META`.

    Args:
        base: contra o que a variacao principal e calculada.
            ``'alinhada'`` (**padrao**) usa ``meta_alinhada`` -- a leitura de
            periodo casado, que e a decidida para a UI e a adotada em D2/D3 do
            `01_kpis.md`. ``'anual'`` usa ``meta_anual``, que e como os numeros do
            briefing foram publicados.

    **As duas leituras divergem em 2026 e o sinal chega a inverter** -- por isso as
    duas vem sempre no DataFrame, em colunas proprias:

    | metrica (2026, 8m) | `variacao_*_alinhada` | `variacao_*_anual` (publicado) |
    |---|---|---|
    | Faturamento | +2,9% | −31,2% (sem sentido) |
    | Inadimplencia > 30d | **+1,22 p.p.** (meta de ago = 8,80%) | +2,02 p.p. (meta de dez = 8,00%) |

    A `Revisao 2026` travou jan-mar no realizado: e isso que aproxima a meta do
    periodo parcial do realizado e afasta as duas leituras. Em anos cheios (2024,
    2025) elas coincidem.

    ``variacao_pct`` so e preenchida para metricas em BRL; em metricas ``%`` a
    leitura correta e ``variacao_abs``, ja em pontos percentuais.
    """
    if base not in ("alinhada", "anual"):
        raise ValueError(f"base invalida: {base!r}. Use 'alinhada' ou 'anual'.")
    disponiveis = tuple(tipos) if tipos else TIPOS_META
    desconhecidos = [t for t in disponiveis if t not in TIPOS_META]
    if desconhecidos:
        raise ValueError(
            f"tipo_meta fora do escopo: {desconhecidos}. Use um de {list(TIPOS_META)}."
        )
    linhas: list[dict] = []
    for tipo in disponiveis:
        if nivel != "Empresa" and tipo in SO_EMPRESA:
            continue
        alvo_mensal = metas_mensais(tipo, ano, nivel, chave)
        if alvo_mensal.empty:
            continue
        agregacao = str(alvo_mensal["tipo_agregacao"].iloc[0])
        unidade = str(alvo_mensal["unidade"].iloc[0])
        versao = str(alvo_mensal["versao_meta"].iloc[0])

        real = realizado_mensal(tipo, ano, nivel, chave)
        real = real.dropna(subset=["realizado"])
        if real.empty:
            continue
        meses = sorted(real["ano_mes"].tolist())
        janela = [m for m in alvo_mensal["ano_mes"] if meses[0] <= m <= meses[-1]]
        real_janela = real[real["ano_mes"].isin(janela)].sort_values("ano_mes")
        alvo_janela = alvo_mensal[alvo_mensal["ano_mes"].isin(janela)].sort_values("ano_mes")

        realizado = _consolidar(real_janela, "realizado", agregacao)
        alvo_alinhada = _consolidar(alvo_janela, "meta", agregacao)

        anual = meta_anual(tipo, ano, nivel, chave)
        valor_anual = float(anual["meta"].iloc[0]) if not anual.empty else float("nan")

        var_abs_alinhada = realizado - alvo_alinhada
        var_abs_anual = realizado - valor_anual
        comparavel = alvo_alinhada if base == "alinhada" else valor_anual
        rotulo_base = (
            f"periodo alinhado ({janela[0]}..{janela[-1]})" if base == "alinhada"
            else "meta anual (periodo cheio)"
        )
        percentual = unidade == "%"
        linhas.append(
            {
                "tipo_meta": tipo,
                "unidade": unidade,
                "tipo_agregacao": agregacao,
                "versao_meta": versao,
                "meses_realizados": len(janela),
                "periodo_realizado": f"{janela[0]}..{janela[-1]}" if janela else "",
                "eh_parcial": len(alvo_mensal) > len(janela),
                "realizado": realizado,
                "meta_alinhada": alvo_alinhada,
                "meta_anual": valor_anual,
                "meta_comparavel": comparavel,
                "base_comparacao": rotulo_base,
                "variacao_abs": realizado - comparavel,
                "variacao_pct": _variacao_pct(realizado - comparavel, comparavel, percentual),
                "variacao_abs_alinhada": var_abs_alinhada,
                "variacao_pct_alinhada": _variacao_pct(var_abs_alinhada, alvo_alinhada, percentual),
                "variacao_abs_anual": var_abs_anual,
                "variacao_pct_anual": _variacao_pct(var_abs_anual, valor_anual, percentual),
            }
        )
    return pd.DataFrame(linhas)


def _variacao_pct(variacao_abs: float, base: float, percentual: bool) -> float:
    """Variacao relativa -- ``NaN`` para metrica percentual (leia ``variacao_abs``, em p.p.)."""
    if percentual or not base or pd.isna(base):
        return float("nan")
    return 100.0 * variacao_abs / base


def comparativo_por_segmento(tipo_meta: str, ano: int) -> pd.DataFrame:
    """Realizado x meta por segmento, para as 3 metricas que tem esse recorte.

    Colunas: ``segmento``, ``realizado``, ``meta_alinhada``, ``meta_anual``,
    ``variacao_abs``, ``variacao_pct``, ``meses_realizados``.

    Levanta ``ValueError`` para Custo Operacional e Inadimplencia > 30d: elas so
    tem meta no nivel Empresa porque o custo de veiculo ocioso nao tem segmento
    (armadilha 6). Sobram Faturamento, Receita Liquida e Recebimento (Caixa).
    """
    if tipo_meta in SO_EMPRESA:
        raise ValueError(
            f"'{tipo_meta}' nao tem meta por segmento (armadilha 6: custo de "
            "veiculo ocioso nao tem contrato, logo nao tem segmento)."
        )
    segmentos = db.consultar(
        """
        select distinct chave_nivel as segmento from public.metas
        where nivel_analise = 'Segmento' and eh_versao_vigente and ano = :ano
        order by 1
        """,
        {"ano": ano},
        ttl=config.TTL_DIMENSOES,
    )["segmento"].tolist()
    partes = [
        comparativo_anual(ano, "Segmento", seg, tipos=(tipo_meta,)).assign(segmento=seg)
        for seg in segmentos
    ]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    colunas = [
        "segmento", "realizado", "meta_alinhada", "meta_anual", "meta_comparavel",
        "variacao_abs", "variacao_pct", "meses_realizados",
    ]
    return df[colunas].sort_values("variacao_pct", ascending=False).reset_index(drop=True)


def versoes_orcamento(ano: int | None = None) -> pd.DataFrame:
    """As versoes de orcamento lado a lado -- a armadilha 3 exposta, nao escondida.

    Colunas: ``ano``, ``versao_meta``, ``eh_versao_vigente``, ``tipo_meta``,
    ``valor_meta_anual``, ``unidade``.

    Em 2026 mostra ``Orcamento Original`` (nao vigente, 37,80 mi de faturamento)
    ao lado da ``Revisao 2026`` (vigente, 35,82 mi). Somar as duas dobraria o ano
    -- por isso todas as outras funcoes filtram ``eh_versao_vigente``.
    """
    cond, params = "", {}
    if ano is not None:
        cond = " and m.ano = :ano"
        params["ano"] = ano
    sql = f"""
    select m.ano, m.versao_meta, m.eh_versao_vigente, m.tipo_meta,
           m.valor_meta::float8 as valor_meta_anual, m.unidade
    from public.metas m
    where m.granularidade = 'Anual' and m.nivel_analise = 'Empresa'{cond}
    order by m.ano, m.tipo_meta, m.versao_meta
    """
    return db.consultar(sql, params, ttl=config.TTL_FATOS)
