"""Objeto de filtros compartilhado por toda a camada semantica.

Um unico :class:`Filtros` viaja da UI para qualquer funcao de metrica. Ele e
**frozen** (e portanto hashavel) de proposito: e ele que entra na chave de cache
das consultas, entao nao pode mudar depois de criado.

Nem toda metrica respeita todo filtro. Isso nao e descuido -- e definicao de
negocio. A tabela :data:`POLITICA_FILTROS` registra cada excecao e o motivo;
:func:`politica_filtros` devolve a mesma tabela como DataFrame para a UI mostrar
ao usuario o porque de um recorte "nao pegar".

Resumo das excecoes (detalhe em :data:`POLITICA_FILTROS`):

* **Denominador da inadimplencia** ignora ``competencia_ini/fim``: e sempre a
  janela movel dos ultimos 12 meses de competencia contados da data de
  referencia. Se ele obedecesse ao periodo da tela, a metrica deixaria de ser
  comparavel com o numero publicado.
* **Numerador da inadimplencia e o aging** ignoram ``competencia_ini/fim``: sao
  fotos da carteira inteira numa data, nao recortes de competencia. Com o escopo
  reduzido a inadimplencia e **so** essa foto -- nao ha serie retroativa.
* **Custo de ociosidade** ignora ``segmentos``, ``portes``, ``ratings``,
  ``clientes`` e ``tipos_contrato``: o custo de veiculo parado tem
  ``custos.id_contrato IS NULL``, logo nao ha cliente nem segmento a que
  atribui-lo. Filtrar por segmento faria o custo ocioso simplesmente sumir.
* **Metas** ignoram tudo exceto ``segmentos`` (que vira ``chave_nivel``) e o ano:
  a tabela ``metas`` so tem os recortes Empresa e Segmento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Sequence

import pandas as pd

from frotas import config


def _tupla(valores: Iterable[str] | str | None) -> tuple[str, ...]:
    """Normaliza entrada de widget (None, str, list, tuple) para tupla ordenada."""
    if valores is None:
        return ()
    if isinstance(valores, str):
        return (valores,)
    return tuple(dict.fromkeys(str(v) for v in valores))


@dataclass(frozen=True)
class Filtros:
    """Recorte pedido pelo usuario. Imutavel e hashavel (entra na chave de cache).

    Attributes:
        competencia_ini / competencia_fim: intervalo de competencia (o dia e
            irrelevante; competencia e sempre dia 1). ``None`` = extremo do dataset.
        data_ref: data de referencia das metricas point-in-time (inadimplencia,
            aging, carteira). ``None`` = data de extracao (2026-08-31).
        segmentos / portes / ratings / ufs / clientes: recortes de cliente.
        tipos_receita: recorte de ``titulos_receber.tipo_receita``.
        tipos_contrato / status_contrato: recortes de contrato.
        categorias_veiculo: recorte de ``veiculos.categoria`` (so vale onde ha
            veiculo -- receita por veiculo usa rateio de alocacao).
        categorias_custo / tipos_custo: recortes de ``custos``.
        incluir_cancelados: se ``True`` (padrao), ``valor_liquido`` soma tambem os
            titulos cancelados. **E a definicao publicada**: a receita liquida de
            referencia (27,9 / 32,8 / 23,0 mi) inclui cancelados. Com ``False`` a
            receita cai para 26,96 / 30,74 / 22,59 mi, que nao e o publicado.
            Nao confunda com o filtro **point-in-time** de cancelamento
            (:func:`clausula_valida_em`, armadilha 1), que e outro eixo: este diz
            se o titulo cancelado entra na base; aquele diz se ja estava cancelado
            na ``data_ref``.
    """

    competencia_ini: date | None = None
    competencia_fim: date | None = None
    data_ref: date | None = None
    segmentos: tuple[str, ...] = ()
    portes: tuple[str, ...] = ()
    ratings: tuple[str, ...] = ()
    ufs: tuple[str, ...] = ()
    clientes: tuple[str, ...] = ()
    tipos_receita: tuple[str, ...] = ()
    tipos_contrato: tuple[str, ...] = ()
    status_contrato: tuple[str, ...] = ()
    categorias_veiculo: tuple[str, ...] = ()
    categorias_custo: tuple[str, ...] = ()
    tipos_custo: tuple[str, ...] = ()
    incluir_cancelados: bool = True

    @classmethod
    def criar(cls, **kwargs: Any) -> "Filtros":
        """Construtor tolerante ao que os widgets do Streamlit devolvem (listas)."""
        campos_lista = {
            "segmentos", "portes", "ratings", "ufs", "clientes", "tipos_receita",
            "tipos_contrato", "status_contrato", "categorias_veiculo",
            "categorias_custo", "tipos_custo",
        }
        limpos: dict[str, Any] = {}
        for chave, valor in kwargs.items():
            if chave in campos_lista:
                limpos[chave] = _tupla(valor)
            else:
                limpos[chave] = valor
        return cls(**limpos)

    def com(self, **kwargs: Any) -> "Filtros":
        """Copia com alteracoes (``dataclasses.replace`` com normalizacao)."""
        return Filtros.criar(**{**self.como_dicionario(), **kwargs})

    def como_dicionario(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)

    # -- valores efetivos -------------------------------------------------

    @property
    def ref(self) -> date:
        """Data de referencia efetiva das metricas point-in-time."""
        return self.data_ref or config.DATA_EXTRACAO

    @property
    def inicio(self) -> date:
        """Primeira competencia efetiva do recorte."""
        return _primeiro_dia(self.competencia_ini or config.COMPETENCIA_MIN)

    @property
    def fim(self) -> date:
        """Ultima competencia efetiva do recorte."""
        return _primeiro_dia(self.competencia_fim or config.COMPETENCIA_MAX)

    @property
    def tem_recorte_cliente(self) -> bool:
        return bool(self.segmentos or self.portes or self.ratings or self.ufs or self.clientes)


def _primeiro_dia(d: date) -> date:
    return date(d.year, d.month, 1)


# --------------------------------------------------------------------------
# Traducao Filtros -> SQL (sempre parametrizado)
# --------------------------------------------------------------------------

#: Mapa campo do filtro -> expressao SQL, por contexto de consulta.
_EXPRESSOES = {
    "titulo": {
        "tipos_receita": "t.tipo_receita",
    },
    "cliente": {
        "segmentos": "cl.segmento",
        "portes": "cl.porte",
        "ratings": "cl.rating_credito",
        "ufs": "cl.uf",
        "clientes": "cl.id_cliente",
    },
    "contrato": {
        "tipos_contrato": "ct.tipo_contrato",
        "status_contrato": "ct.status_contrato",
    },
    "veiculo": {
        "categorias_veiculo": "v.categoria",
    },
    "custo": {
        "categorias_custo": "cs.categoria_custo",
        "tipos_custo": "cs.tipo_custo",
    },
}


def _adicionar(
    filtros: Filtros,
    contextos: Sequence[str],
    condicoes: list[str],
    params: dict[str, Any],
) -> None:
    for contexto in contextos:
        for campo, expressao in _EXPRESSOES[contexto].items():
            valores: tuple[str, ...] = getattr(filtros, campo)
            if valores:
                params[campo] = valores
                condicoes.append(f"{expressao} in :{campo}")


def condicoes_titulos(
    filtros: Filtros,
    *,
    contextos: Sequence[str] = ("titulo", "cliente", "contrato"),
    com_periodo: bool = True,
    com_cancelados: bool | None = None,
) -> tuple[str, dict[str, Any]]:
    """Monta o ``WHERE`` de uma consulta sobre ``titulos_receber``.

    Args:
        filtros: recorte do usuario.
        contextos: quais grupos de filtro aplicar. Uma consulta que nao junta
            ``contratos`` deve omitir ``"contrato"``.
        com_periodo: aplica o intervalo de competencia. As metricas point-in-time
            passam ``False`` -- elas olham a carteira inteira numa data.
        com_cancelados: sobrescreve ``filtros.incluir_cancelados``; quando
            ``False``, exclui titulos com ``data_cancelamento`` preenchida.

    Returns:
        ``(clausula, params)`` -- a clausula ja vem prefixada com ``and`` quando
        nao esta vazia, para colar depois de um ``where 1=1``.
    """
    condicoes: list[str] = []
    params: dict[str, Any] = {}
    if com_periodo:
        condicoes.append("t.competencia between cast(:comp_ini as date) and cast(:comp_fim as date)")
        params["comp_ini"] = filtros.inicio
        params["comp_fim"] = filtros.fim
    _adicionar(filtros, contextos, condicoes, params)
    incluir = filtros.incluir_cancelados if com_cancelados is None else com_cancelados
    if not incluir:
        condicoes.append("t.data_cancelamento is null")
    return _juntar(condicoes), params


def condicoes_custos(
    filtros: Filtros,
    *,
    contextos: Sequence[str] = ("custo", "veiculo"),
    com_periodo: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Monta o ``WHERE`` de uma consulta sobre ``custos``.

    Nao inclui ``"cliente"``/``"contrato"`` por padrao: aplicar recorte de cliente
    a custos elimina silenciosamente o custo de veiculo ocioso
    (``custos.id_contrato IS NULL``), que e justamente um dos numeros que o app
    precisa mostrar. Quem quiser o recorte por segmento deve pedi-lo
    explicitamente e assumir a perda do ocioso.
    """
    condicoes: list[str] = []
    params: dict[str, Any] = {}
    if com_periodo:
        condicoes.append("cs.competencia between cast(:comp_ini as date) and cast(:comp_fim as date)")
        params["comp_ini"] = filtros.inicio
        params["comp_fim"] = filtros.fim
    _adicionar(filtros, contextos, condicoes, params)
    return _juntar(condicoes), params


def _juntar(condicoes: Sequence[str]) -> str:
    return ("\n  and " + "\n  and ".join(condicoes)) if condicoes else ""


def clausula_valida_em(alias: str = "t", param: str = "ref") -> str:
    """Filtro point-in-time de cancelamento: o titulo existia na data ``:ref``?

    Armadilha 1 do briefing. Um titulo cancelado em out/2025 conta como valido
    numa foto de set/2025 e nao conta numa foto de dez/2025. Ignorar isso infla a
    inadimplencia de 9,4% para 18,7% em jun/2026.
    """
    return f"({alias}.data_cancelamento is null or {alias}.data_cancelamento > cast(:{param} as date))"


def clausula_nao_pago_em(alias: str = "t", param: str = "ref") -> str:
    """O titulo ainda estava em aberto na data ``:ref``? (armadilha 2: recalcular)."""
    return f"({alias}.data_pagamento is null or {alias}.data_pagamento > cast(:{param} as date))"


def clausula_nao_baixado_em(alias: str = "t", param: str = "ref") -> str:
    """O titulo ainda estava na carteira (sem baixa) na data ``:ref``?

    Sutileza do dataset: 4 titulos ja marcados ``Baixado`` na foto de extracao
    tem ``data_baixa`` **posterior** a 2026-08-31 (a baixa e lancada em
    venc + 370..430 dias). O razao de 2026-08-31 ja os tirou da carteira -- e o
    aging publicado (180+ = 0,82 mi) os exclui. Por isso, para qualquer ``:ref``
    igual ou posterior a extracao, todo titulo com baixa registrada sai; antes
    disso vale o ponto no tempo. Sem essa clausula o balde 180+ da 1,00 mi.
    """
    return (
        f"({alias}.data_baixa is null or ({alias}.data_baixa > cast(:{param} as date) "
        f"and cast(:{param} as date) < cast(:data_extracao as date)))"
    )


# --------------------------------------------------------------------------
# Politica: que metrica ignora que filtro, e por que
# --------------------------------------------------------------------------

POLITICA_FILTROS: tuple[tuple[str, str, str], ...] = (
    (
        "credito.inadimplencia_ponto_no_tempo (denominador)",
        "competencia_ini, competencia_fim",
        "O denominador e a janela movel fixa de 12 meses de competencia contados "
        "de data_ref. Deixar a tela mexer nela quebraria a comparabilidade com o "
        "numero publicado e com a serie historica.",
    ),
    (
        "credito.inadimplencia_ponto_no_tempo (numerador), credito.aging_carteira, "
        "credito.aging_por_cliente, credito.risco_por_rating, credito.risco_por_segmento, "
        "credito.risco_por_cliente, credito.titulos_em_risco_de_baixa, "
        "credito.titulos_com_baixa_futura",
        "competencia_ini, competencia_fim",
        "Sao fotos da carteira inteira em data_ref: um titulo de 2024 ainda "
        "vencido conta na foto de 2026. Recortar por competencia esconderia "
        "exatamente o atraso antigo que a metrica existe para revelar.",
    ),
    (
        "custos.custo_ociosidade",
        "segmentos, portes, ratings, ufs, clientes, tipos_contrato, status_contrato",
        "Custo de veiculo ocioso tem custos.id_contrato IS NULL (armadilha 6): "
        "nao ha cliente nem segmento a que atribuir. Aplicar o recorte zeraria a "
        "metrica em vez de filtra-la.",
    ),
    (
        "custos.custos_por_competencia, custos.custos_por_ano, "
        "custos.custos_por_dimensao",
        "nenhum, mas TROCAM DE FONTE com recorte de cliente ou de contrato",
        "Sem recorte, o total inclui o ocioso e reproduz 18,3 / 21,5 / 15,6 mi. "
        "Com recorte a fonte passa a ser so o custo alocado a contrato (o patio "
        "sai, armadilha 6): custo_ocioso_incluido volta False e escopo vira "
        "'contratos'. A UI tem de exibir esse aviso e esconder o gauge de meta.",
    ),
    (
        "receita.faturamento_por_dimensao(dimensao='categoria_veiculo'), "
        "receita.faturamento_por_categoria_veiculo",
        "nenhum (mas usa rateio)",
        "Titulo nao tem veiculo: a receita e rateada em partes iguais entre os "
        "veiculos alocados ao contrato na competencia do titulo. E aproximacao, "
        "nao fato -- a coluna rateada vem sinalizada no nome.",
    ),
    (
        "metas.*",
        "tudo, exceto segmentos (via chave_nivel) e o periodo anual",
        "A tabela metas so tem os niveis Empresa e Segmento; nao existe meta por "
        "cliente, rating ou categoria de veiculo. Filtrar o realizado sem filtrar "
        "a meta produziria variacao falsa.",
    ),
    (
        "alertas.avaliar (janelas temporais)",
        "competencia_ini, competencia_fim",
        "As regras de 12 meses (A4, A16) usam sempre a janela movel que termina "
        "em data_ref, e as de meta (A1, A3, A6) usam o ano de data_ref. "
        "Um alerta que muda de cor conforme o zoom da tela nao e alerta. Recortes "
        "dimensionais sao respeitados; onde a regra deixa de valer, o nivel volta "
        "'indisponivel' com o motivo.",
    ),
    (
        "dimensoes.*",
        "todos",
        "Listas de filtro mostram o dominio completo do banco; se dependessem do "
        "recorte atual o usuario nao conseguiria sair de um filtro vazio.",
    ),
)


def politica_filtros() -> pd.DataFrame:
    """Tabela 'que metrica ignora que filtro, e por que', pronta para a UI."""
    return pd.DataFrame(
        POLITICA_FILTROS, columns=["metrica", "filtros_ignorados", "motivo"]
    )
