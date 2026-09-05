"""Metricas de custo operacional e de ociosidade da frota.

Escopo do modulo (reduzido): **custo**. Margem operacional saiu do projeto por
completo -- existe no banco, mas nao aqui. Nao ha margem por competencia, por
ano, por contrato, por veiculo nem por categoria de veiculo, e nao ha analise de
manutencao corretiva. O que fica e o custo, suas quebras e o custo do patio.

Definicao canonica (reproduz o publicado no briefing):

* **Custo operacional** = ``sum(custos.valor)`` por competencia, **incluindo** as
  linhas de veiculo ocioso (``custos.id_contrato IS NULL``).
  2024 = 18,26 mi · 2025 = 21,47 mi · 2026 (8m) = 15,58 mi.

**Armadilha 6 e a regra mais importante deste modulo.** Custo de veiculo ocioso
nao tem contrato e, portanto, nao tem cliente nem segmento. Consequencias:

* :func:`custos_por_competencia`, :func:`custos_por_ano` e
  :func:`custos_por_dimensao` incluem o ocioso **enquanto nao houver recorte de
  cliente**. Se o usuario filtrar por segmento, porte, rating, UF, cliente ou
  tipo de contrato, o custo passa a ser so o alocado -- e a coluna
  ``custo_ocioso_incluido`` volta ``False`` (e ``escopo`` vira ``'contratos'``)
  para a UI avisar. Nao ha alternativa honesta: nao existe rateio defensavel do
  patio.
* :func:`custo_ociosidade` e o oposto: so olha as linhas sem contrato, e por isso
  **ignora** todo recorte de cliente -- aplica-lo zeraria a metrica.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from frotas import config, db
from frotas.filtros import Filtros, condicoes_custos

_DE_CUSTO_SIMPLES = """
from public.custos cs
join public.veiculos v on v.id_veiculo = cs.id_veiculo
"""

_DE_CUSTO_ALOCADO = """
from public.custos cs
join public.veiculos v on v.id_veiculo = cs.id_veiculo
join public.contratos ct on ct.id_contrato = cs.id_contrato
join public.clientes cl on cl.id_cliente = ct.id_cliente
"""

#: Dimensoes aceitas por :func:`custos_por_dimensao`.
DIMENSOES: dict[str, tuple[str, str]] = {
    "categoria_custo": ("cs.categoria_custo", "categoria_custo"),
    "tipo_custo": ("cs.tipo_custo", "tipo_custo"),
    "categoria_veiculo": ("v.categoria", "categoria"),
    "marca_modelo": ("v.marca_modelo", "marca_modelo"),
    "veiculo": ("cs.id_veiculo", "id_veiculo"),
}

Dimensao = Literal["categoria_custo", "tipo_custo", "categoria_veiculo", "marca_modelo", "veiculo"]

_MEDIDAS_CUSTO = """
       sum(cs.valor)::float8 as custo_total,
       coalesce(sum(cs.valor) filter (where cs.id_contrato is not null), 0)::float8 as custo_alocado,
       coalesce(sum(cs.valor) filter (where cs.id_contrato is null), 0)::float8 as custo_ocioso,
       coalesce(sum(cs.valor) filter (where cs.tipo_custo = 'Fixo'), 0)::float8 as custo_fixo,
       coalesce(sum(cs.valor) filter (where cs.tipo_custo = 'Variavel'), 0)::float8 as custo_variavel,
       coalesce(sum(cs.valor) filter (where cs.tipo_custo = 'Nao Caixa'), 0)::float8 as custo_nao_caixa
"""


def _escopo(custo_ocioso_incluido: bool) -> str:
    """Rotulo de escopo para a UI (pedido A11 do UX / §9.1 do 01_kpis.md).

    ``'empresa'`` = custo total, com veiculo ocioso -- a metrica publicada, a
    unica com meta. ``'contratos'`` = so custo alocado a contrato; a UI deve
    renomear o KPI para **Custo de Contratos** e esconder o gauge de meta, porque
    o total encolhe (some o patio) e deixa de ser comparavel com o orcamento.
    """
    return "empresa" if custo_ocioso_incluido else "contratos"


def _fonte_custos(filtros: Filtros) -> tuple[str, str, dict, bool]:
    """Escolhe a fonte de custo conforme haja ou nao recorte de cliente.

    Sem recorte de cliente -> custo total (inclui ocioso). Com recorte -> so custo
    alocado a contrato, porque o ocioso nao tem a quem ser atribuido.
    """
    precisa_contrato = bool(
        filtros.tem_recorte_cliente or filtros.tipos_contrato or filtros.status_contrato
    )
    if precisa_contrato:
        contextos = ("custo", "veiculo", "cliente", "contrato")
        cond, params = condicoes_custos(filtros, contextos=contextos)
        return _DE_CUSTO_ALOCADO, cond, params, False
    cond, params = condicoes_custos(filtros)
    return _DE_CUSTO_SIMPLES, cond, params, True


def custos_por_competencia(filtros: Filtros) -> pd.DataFrame:
    """Serie mensal de custo operacional.

    Colunas: ``competencia``, ``ano_mes``, ``ano``, ``custo_total``,
    ``custo_alocado``, ``custo_ocioso``, ``custo_fixo``, ``custo_variavel``,
    ``custo_nao_caixa``, ``qtd_veiculos``, ``custo_ocioso_incluido``.
    """
    de, cond, params, inclui = _fonte_custos(filtros)
    sql = f"""
    select cs.competencia,
           to_char(cs.competencia, 'YYYY-MM') as ano_mes,
           extract(year from cs.competencia)::int as ano,
           {_MEDIDAS_CUSTO.strip()},
           count(distinct cs.id_veiculo) as qtd_veiculos
    {de}
    where 1=1{cond}
    group by 1, 2, 3
    order by 1
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    df["custo_ocioso_incluido"] = inclui
    df["escopo"] = _escopo(inclui)
    return df


def custos_por_ano(filtros: Filtros) -> pd.DataFrame:
    """Custo operacional consolidado por ano de competencia.

    Colunas: ``ano``, ``meses``, ``eh_parcial``, ``custo_total``,
    ``custo_alocado``, ``custo_ocioso``, ``custo_fixo``, ``custo_variavel``,
    ``custo_nao_caixa``, ``custo_ocioso_incluido``.
    """
    de, cond, params, inclui = _fonte_custos(filtros)
    sql = f"""
    select extract(year from cs.competencia)::int as ano,
           count(distinct cs.competencia) as meses,
           {_MEDIDAS_CUSTO.strip()}
    {de}
    where 1=1{cond}
    group by 1
    order by 1
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    df["eh_parcial"] = df["meses"] < 12
    df["custo_ocioso_incluido"] = inclui
    df["escopo"] = _escopo(inclui)
    return df


def custos_por_dimensao(filtros: Filtros, dimensao: Dimensao = "categoria_custo") -> pd.DataFrame:
    """Custo quebrado por categoria, tipo, categoria de veiculo ou modelo.

    Colunas: a coluna da dimensao + ``custo_total``, ``custo_alocado``,
    ``custo_ocioso``, ``custo_fixo``, ``custo_variavel``, ``custo_nao_caixa``,
    ``participacao_pct``, ``custo_ocioso_incluido``.

    E aqui que se ve o efeito da frota velha: Manutencao Corretiva concentrada em
    poucos modelos.
    """
    if dimensao not in DIMENSOES:
        raise ValueError(f"dimensao invalida: {dimensao!r}. Use uma de {sorted(DIMENSOES)}.")
    expressao, rotulo = DIMENSOES[dimensao]
    de, cond, params, inclui = _fonte_custos(filtros)
    sql = f"""
    select {expressao} as {rotulo},
           {_MEDIDAS_CUSTO.strip()}
    {de}
    where 1=1{cond}
    group by 1
    order by custo_total desc
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    total = df["custo_total"].sum()
    df["participacao_pct"] = 100.0 * df["custo_total"] / total if total else 0.0
    df["custo_ocioso_incluido"] = inclui
    df["escopo"] = _escopo(inclui)
    return df


def custo_ociosidade(filtros: Filtros) -> pd.DataFrame:
    """Custo de veiculo parado, por competencia.

    Colunas: ``competencia``, ``ano_mes``, ``custo_ocioso``,
    ``qtd_veiculos_ociosos``, ``qtd_veiculos_frota``, ``taxa_ociosidade_pct``,
    ``custo_total``, ``pct_do_custo_total``.

    ``taxa_ociosidade_pct`` = veiculos sem contrato no mes / veiculos com custo no
    mes. Reproduz o publicado: nov/25 **6,7%** · fev/26 **6,4%** · jul/26 4,6% ·
    ago/26 **6,3% (15 de 239)**. Grao mensal: um veiculo alocado no dia 20 conta o
    mes inteiro como alocado.

    Definicao: linhas de ``custos`` com ``id_contrato IS NULL`` (armadilha 6).

    Filtros ignorados: **todos os de cliente** (segmento, porte, rating, UF,
    cliente) e os de contrato -- por definicao nao existe contrato nessas linhas.
    Aplicar o recorte nao filtraria a metrica, zeraria. Os filtros de competencia,
    categoria de custo, tipo de custo e categoria de veiculo continuam valendo.
    """
    cond, params = condicoes_custos(filtros)
    sql = f"""
    select cs.competencia,
           to_char(cs.competencia, 'YYYY-MM') as ano_mes,
           coalesce(sum(cs.valor) filter (where cs.id_contrato is null), 0)::float8 as custo_ocioso,
           count(distinct cs.id_veiculo) filter (where cs.id_contrato is null) as qtd_veiculos_ociosos,
           count(distinct cs.id_veiculo) as qtd_veiculos_frota,
           sum(cs.valor)::float8 as custo_total
    {_DE_CUSTO_SIMPLES}
    where 1=1{cond}
    group by 1, 2
    order by 1
    """
    df = db.consultar(sql, params, ttl=config.TTL_FATOS)
    df["pct_do_custo_total"] = (
        100.0 * df["custo_ocioso"] / df["custo_total"].replace(0, pd.NA)
    )
    df["taxa_ociosidade_pct"] = (
        100.0 * df["qtd_veiculos_ociosos"] / df["qtd_veiculos_frota"].replace(0, pd.NA)
    )
    return df


