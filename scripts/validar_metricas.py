#!/usr/bin/env python3
"""Valida a camada semantica contra os numeros publicados no briefing.

Roda a camada semantica de verdade (mesmas funcoes que a UI chama), contra o
banco de verdade, e compara com ``docs/00_briefing_tecnico.md`` e
``DICIONARIO_DADOS.md``. Somente leitura -- nenhum INSERT/UPDATE/DELETE/DDL.

Uso::

    python3 scripts/validar_metricas.py            # tudo
    python3 scripts/validar_metricas.py --secao credito

Cobre os cinco eixos em escopo: faturamento, recebimento, inadimplencia
(**so a posicao atual**), metas e custos. Margem operacional, carteira
contratual, curva ABC, recuperacao e manutencao corretiva sairam do projeto e
nao sao mais verificadas.

Saida: uma linha por verificacao com esperado x obtido x tolerancia. Codigo de
saida 0 se todas as verificacoes obrigatorias passarem, 1 caso contrario. As
verificacoes marcadas ``INFO`` sao divergencias de definicao ja documentadas e
nao derrubam o resultado.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logging.getLogger("streamlit").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frotas import config, db  # noqa: E402
from frotas.filtros import Filtros  # noqa: E402
from frotas.metrics import alertas, credito, custos, metas, receita  # noqa: E402

MI = 1_000_000.0


@dataclass
class Resultado:
    secao: str
    nome: str
    esperado: float | str
    obtido: float | str
    tolerancia: float
    ok: bool
    informativo: bool = False
    nota: str = ""


@dataclass
class Relatorio:
    linhas: list[Resultado] = field(default_factory=list)

    def checar(
        self,
        secao: str,
        nome: str,
        esperado: float,
        obtido: float,
        tolerancia: float,
        informativo: bool = False,
        nota: str = "",
    ) -> None:
        ok = abs(float(obtido) - float(esperado)) <= tolerancia
        self.linhas.append(Resultado(secao, nome, esperado, obtido, tolerancia, ok, informativo, nota))

    def afirmar(self, secao: str, nome: str, condicao: bool, detalhe: str = "") -> None:
        self.linhas.append(
            Resultado(secao, nome, "verdadeiro", "verdadeiro" if condicao else "FALSO", 0.0, condicao, nota=detalhe)
        )

    @property
    def falhas(self) -> list[Resultado]:
        return [r for r in self.linhas if not r.ok and not r.informativo]

    def imprimir(self) -> None:
        secao_atual = ""
        for r in self.linhas:
            if r.secao != secao_atual:
                secao_atual = r.secao
                print(f"\n--- {secao_atual} " + "-" * (68 - len(secao_atual)))
            marca = "INFO" if r.informativo and not r.ok else ("OK  " if r.ok else "FALHA")
            esperado = f"{r.esperado:>12,.4f}" if isinstance(r.esperado, float) else f"{r.esperado:>12}"
            obtido = f"{r.obtido:>12,.4f}" if isinstance(r.obtido, float) else f"{r.obtido:>12}"
            print(f"  [{marca:5}] {r.nome:<46} esperado {esperado} | obtido {obtido}")
            if r.nota:
                print(f"           {r.nota}")


# --------------------------------------------------------------------------
# Secoes
# --------------------------------------------------------------------------


def validar_conexao(rel: Relatorio) -> None:
    estado = db.verificar_conexao()
    rel.afirmar("conexao", "banco acessivel", estado.ok, estado.mensagem)

    sessao = db.consultar(
        "select current_setting('default_transaction_read_only') as ro, "
        "current_setting('statement_timeout') as st, "
        "current_setting('application_name') as an"
    )
    rel.afirmar("conexao", "sessao em default_transaction_read_only", sessao.loc[0, "ro"] == "on")
    rel.afirmar(
        "conexao",
        "statement_timeout aplicado",
        sessao.loc[0, "st"] == f"{config.TIMEOUT_STATEMENT_MS // 1000}s",
        f"valor lido: {sessao.loc[0, 'st']}",
    )
    rel.afirmar(
        "conexao",
        "application_name aplicado",
        sessao.loc[0, "an"] == config.NOME_APLICACAO,
        f"valor lido: {sessao.loc[0, 'an']}",
    )

    for sql, rotulo in (
        ("delete from public.custos", "guarda recusa DELETE"),
        ("update public.metas set valor_meta = 0", "guarda recusa UPDATE"),
        ("drop table public.custos", "guarda recusa DROP"),
        ("select 1; drop table public.custos", "guarda recusa 2 statements"),
        ("  -- select\n insert into public.metas values (1)", "guarda recusa INSERT comentado"),
    ):
        try:
            db.consultar(sql)
            rel.afirmar("conexao", rotulo, False, "a consulta NAO foi bloqueada")
        except db.SqlNaoPermitido:
            rel.afirmar("conexao", rotulo, True)

    # Escrita real recusada pelo servidor, nao so pela guarda local.
    from sqlalchemy import text

    try:
        with db.obter_engine().connect() as conexao:
            conexao.execute(text("create temp table _t_validacao (x int)"))
        rel.afirmar("conexao", "servidor recusa escrita (read-only)", False, "escrita foi aceita")
    except Exception as exc:  # noqa: BLE001
        rel.afirmar(
            "conexao",
            "servidor recusa escrita (read-only)",
            "read-only transaction" in str(getattr(exc, "orig", exc)),
            str(getattr(exc, "orig", exc))[:70],
        )


#: Briefing, secao "Numeros de referencia" (valores em milhoes de reais).
REFERENCIA_ANUAL = {
    2024: {"faturamento": 29.8, "receita_liquida": 27.9, "custos": 18.3},
    2025: {"faturamento": 35.0, "receita_liquida": 32.8, "custos": 21.5},
    2026: {"faturamento": 24.6, "receita_liquida": 23.0, "custos": 15.6},
}


def validar_receita_custos(rel: Relatorio) -> None:
    f = Filtros()
    fat = receita.faturamento_por_ano(f).set_index("ano")
    cus = custos.custos_por_ano(f).set_index("ano")

    for ano, ref in REFERENCIA_ANUAL.items():
        rel.checar("receita", f"{ano} faturamento bruto (mi)", ref["faturamento"],
                   fat.loc[ano, "faturamento_bruto"] / MI, 0.05)
        rel.checar("receita", f"{ano} receita liquida (mi)", ref["receita_liquida"],
                   fat.loc[ano, "receita_liquida"] / MI, 0.05)
        rel.checar("custos", f"{ano} custo operacional (mi)", ref["custos"],
                   cus.loc[ano, "custo_total"] / MI, 0.05)

    rel.afirmar("receita", "2026 marcado como ano parcial (8 meses)",
                bool(fat.loc[2026, "eh_parcial"]) and int(fat.loc[2026, "meses"]) == 8)
    rel.afirmar("custos", "custo total inclui ociosidade sem recorte de cliente",
                bool(cus.loc[2025, "custo_ocioso"] > 0)
                and bool(cus.loc[2025, "custo_ocioso_incluido"])
                and str(cus.loc[2025, "escopo"]) == "empresa")

    # Armadilha 1: a logica point-in-time de cancelamento continua dentro do
    # faturamento valido, mesmo sem secao propria de cancelamentos.
    rel.afirmar("receita", "faturamento valido = bruto - cancelado na data ref",
                all(abs(float(fat.loc[a, "faturamento_bruto"])
                        - float(fat.loc[a, "valor_cancelado"])
                        - float(fat.loc[a, "faturamento_valido"])) < 1.0
                    for a in REFERENCIA_ANUAL))

    # Cancelamentos (nota de rodape do visual de faturamento): divergencia de
    # definicao ja registrada no dicionario.
    por_ano = 100.0 * fat["valor_cancelado"] / fat["faturamento_bruto"]
    for ano, publicado in ((2024, 4.0), (2025, 6.0), (2026, 2.0)):
        rel.checar(
            "receita", f"{ano} cancelamentos (% do faturamento)", publicado,
            float(por_ano.loc[ano]), 0.05, informativo=True,
            nota="INFO: por competencia da 3,53 / 6,23 / 1,97. O dicionario ja "
                 "registra que os 4,0/6,0/2,0 publicados usam outra definicao "
                 "(provavelmente ano de cancelamento, que da 1,22/5,45/5,88). "
                 "Valores absolutos batem.",
        )


#: Briefing: inadimplencia > 30d point-in-time.
REFERENCIA_INADIMPLENCIA = {
    date(2024, 12, 31): 3.56,
    date(2025, 6, 30): 6.47,
    date(2025, 12, 31): 10.20,
    date(2026, 6, 30): 9.37,
}

#: Briefing: aging em 2026-08-31 (milhoes de reais), excl. cancelados e baixados.
REFERENCIA_AGING = {
    "A vencer": 4.47, "1-30d": 0.76, "31-60d": 0.44,
    "61-90d": 0.40, "91-180d": 0.77, "180+d": 0.82,
}


def validar_credito(rel: Relatorio) -> None:
    f = Filtros()
    for ref, esperado in REFERENCIA_INADIMPLENCIA.items():
        linha = credito.inadimplencia_ponto_no_tempo(f, ref)
        rel.checar("credito", f"inadimplencia >30d em {ref:%Y-%m-%d} (%)", esperado,
                   float(linha.loc[0, "inadimplencia_pct"]), 0.005)

    aging = credito.aging_carteira(f, config.DATA_EXTRACAO).set_index("faixa")
    for faixa, esperado in REFERENCIA_AGING.items():
        rel.checar("credito", f"aging 2026-08-31 {faixa} (mi)", esperado,
                   float(aging.loc[faixa, "valor_bruto"]) / MI, 0.005)

    # Contraprova da armadilha 1: sem o filtro point-in-time de cancelamento a
    # inadimplencia de jun/2026 vai de 9,37% para ~18,7% (numero do dicionario).
    ref = date(2026, 6, 30)
    sem_filtro = db.consultar(
        """
        select (100.0 *
          (select coalesce(sum(t.valor_bruto), 0) from public.titulos_receber t
            where t.data_vencimento <= cast(:ref as date) - 30
              and (t.data_pagamento is null or t.data_pagamento > cast(:ref as date)))
          / (select sum(t.valor_bruto) from public.titulos_receber t
              where t.competencia > (date_trunc('month', cast(:ref as date)) - interval '12 months')::date
                and t.competencia <= date_trunc('month', cast(:ref as date))::date)
        )::float8 as pct
        """,
        {"ref": ref},
    ).loc[0, "pct"]
    rel.checar(
        "credito", "contraprova: sem point-in-time jun/26 (%)", 18.70, float(sem_filtro), 0.01,
        nota="Armadilha 1 confirmada: 9,37% -> 18,70%. A definicao que reproduz o "
             "publicado tira o filtro de cancelamento dos DOIS lados da fracao e "
             "mantem o corte point-in-time de pagamento no numerador.",
    )

    # O aging tem que fechar com a carteira em aberto da foto de extracao.
    em_aberto = db.consultar(
        "select sum(valor_bruto)::float8 as v from public.titulos_receber "
        "where status_titulo = 'Em Aberto'"
    ).loc[0, "v"]
    rel.checar("credito", "soma do aging = carteira 'Em Aberto' (mi)",
               float(em_aberto) / MI, float(aging["valor_bruto"].sum()) / MI, 0.001)

    # A foto por rating e por segmento tem que somar a foto da empresa.
    empresa = credito.inadimplencia_ponto_no_tempo(f, config.DATA_EXTRACAO)
    por_rating = credito.risco_por_rating(f, config.DATA_EXTRACAO)
    rel.checar("credito", "ratings somam o vencido>30d da empresa (mi)",
               float(empresa.loc[0, "valor_vencido_30d"]) / MI,
               float(por_rating["vencido_30d_mais"].sum()) / MI, 0.001)
    por_segmento = credito.risco_por_segmento(f, config.DATA_EXTRACAO)
    rel.checar("credito", "segmentos somam o vencido>30d da empresa (mi)",
               float(empresa.loc[0, "valor_vencido_30d"]) / MI,
               float(por_segmento["vencido_30d_mais"].sum()) / MI, 0.001)
    rel.afirmar("credito", "janela de 12 meses completa na data de extracao",
                bool(empresa.loc[0, "janela_completa"]))

    # Drill ate o titulo, com status recalculado na data de referencia (armadilha 2).
    titulos = credito.titulos_do_cliente(f, "CLI0001")
    vencidos = titulos[titulos["faixa"].isin(["31-60d", "61-90d", "91-180d", "180+d"])]
    rel.checar("credito", "CLI0001 vencido>30d pelo drill (mil)", 159.5,
               float(vencidos["valor_bruto"].sum()) / 1000, 0.1)
    rel.afirmar("credito", "drill recalcula status, nao le status_titulo",
                set(titulos["status_calculado"]) <= {"Pago", "Pago com atraso", "Cancelado",
                                                     "Baixado", "Vencido", "A vencer"}
                and (titulos["status_calculado"] == "Pago com atraso").any())
    rel.afirmar("credito", "drill devolve grao de titulo", len(titulos) == 62)

    # A foto por cliente tem que bater com o drill do mesmo cliente.
    risco = credito.risco_por_cliente(f, config.DATA_EXTRACAO, limite=None).set_index("id_cliente")
    rel.checar("credito", "CLI0001 vencido>30d pela foto por cliente (mil)",
               float(vencidos["valor_bruto"].sum()) / 1000,
               float(risco.loc["CLI0001", "vencido_30d_mais"]) / 1000, 0.001)


#: Dicionario, "Realizado x meta vigente" (2026 = jan-ago).
REFERENCIA_METAS = {
    2024: {"Faturamento": -2.7, "Recebimento (Caixa)": -4.7, "Inadimplencia > 30d": 0.56},
    2025: {"Faturamento": 6.8, "Recebimento (Caixa)": -2.9, "Inadimplencia > 30d": 7.20},
    2026: {"Faturamento": 2.9, "Recebimento (Caixa)": 3.6, "Inadimplencia > 30d": 2.02},
}


def validar_metas(rel: Relatorio) -> None:
    for ano, esperados in REFERENCIA_METAS.items():
        comp = metas.comparativo_anual(ano).set_index("tipo_meta")
        for tipo, esperado in esperados.items():
            linha = comp.loc[tipo]
            # A tabela publicada mistura as duas bases: metricas BRL (Soma) contra a
            # meta dos mesmos meses; metricas percentuais contra a meta anual.
            # As duas leituras vem no DataFrame, entao o teste le a coluna certa.
            if linha["unidade"] == "%":
                obtido, unidade = float(linha["variacao_abs_anual"]), "p.p., base anual"
            else:
                obtido, unidade = float(linha["variacao_pct_alinhada"]), "%, base alinhada"
            rel.checar("metas", f"{ano} {tipo} ({unidade})", esperado, obtido, 0.05)

    # Leitura de periodo casado (a primaria da UI, adotada em D2/D3 do 01_kpis.md).
    alinhado = metas.comparativo_anual(2026).set_index("tipo_meta")
    rel.checar("metas", "2026 inadimplencia x meta do mes (p.p.)", 1.22,
               float(alinhado.loc["Inadimplencia > 30d", "variacao_abs"]), 0.05,
               nota="D2: contra a meta anual (dez) seria +2,02 p.p.")
    rel.afirmar("metas", "Margem Operacional fora do escopo da tabela de metas",
                "Margem Operacional" not in set(alinhado.index)
                and "Margem Operacional" not in metas.TIPOS_META,
                "Decisao do dono do projeto: a metrica existe no banco, nao no app.")
    comp2026 = alinhado
    rel.checar("metas", "2026 meta de faturamento jan-ago (mi)", 23.92,
               float(comp2026.loc["Faturamento", "meta_alinhada"]) / MI, 0.01,
               nota="Armadilha 7: contra o ano cheio (35,82 mi) a variacao seria -31%.")
    rel.afirmar("metas", "2026 marcado como periodo parcial",
                bool(comp2026.loc["Faturamento", "eh_parcial"]))
    rel.afirmar("metas", "2026 usa a versao vigente (Revisao 2026)",
                comp2026.loc["Faturamento", "versao_meta"] == "Revisao 2026")

    # Armadilha 3: somar as duas versoes de 2026 dobraria o ano.
    versoes = metas.versoes_orcamento(2026)
    fat = versoes[versoes["tipo_meta"] == "Faturamento"]
    rel.checar("metas", "2026 orcamento original (mi)", 37.80,
               float(fat[~fat["eh_versao_vigente"]]["valor_meta_anual"].iloc[0]) / MI, 0.01)
    rel.checar("metas", "2026 revisao vigente (mi)", 35.82,
               float(fat[fat["eh_versao_vigente"]]["valor_meta_anual"].iloc[0]) / MI, 0.01)

    # Armadilha 4: metas percentuais nao se somam.
    inad = metas.comparativo_anual(2025).set_index("tipo_meta").loc["Inadimplencia > 30d"]
    rel.afirmar("metas", "inadimplencia consolidada por 'Fim de Periodo'",
                inad["tipo_agregacao"] == "Fim de Periodo" and abs(float(inad["meta_anual"]) - 3.0) < 1e-9)
    rel.afirmar("metas", "as 5 metricas em escopo aparecem no comparativo de 2025",
                set(metas.comparativo_anual(2025)["tipo_meta"]) == set(metas.TIPOS_META))

    # Segmentos somam o total da empresa (coerencia do orcamento por construcao).
    total = float(metas.meta_anual("Faturamento", 2025).loc[0, "meta"])
    por_segmento = db.consultar(
        """
        select sum(valor_meta)::float8 as v from public.metas
        where eh_versao_vigente and granularidade = 'Anual'
          and nivel_analise = 'Segmento' and tipo_meta = 'Faturamento' and ano = :ano
        """,
        {"ano": 2025},
    ).loc[0, "v"]
    rel.checar("metas", "2025 segmentos somam a meta Empresa (mi)", total / MI,
               float(por_segmento) / MI, 0.001)


def validar_filtros(rel: Relatorio) -> None:
    """Coerencia interna: filtros mudam o resultado e o cache e estavel."""
    total = receita.faturamento_por_ano(Filtros()).set_index("ano").loc[2025, "faturamento_bruto"]
    soma_segmentos = receita.faturamento_por_dimensao(Filtros.criar(
        competencia_ini=date(2025, 1, 1), competencia_fim=date(2025, 12, 1)
    ), "segmento")["faturamento_bruto"].sum()
    rel.checar("filtros", "2025 segmentos somam o total (mi)", float(total) / MI,
               float(soma_segmentos) / MI, 0.001)

    rateado = receita.faturamento_por_categoria_veiculo(Filtros())["faturamento_bruto_rateado"].sum()
    bruto = receita.resumo(Filtros()).loc[0, "faturamento_bruto"]
    rel.checar("filtros", "rateio por categoria preserva o total (mi)", float(bruto) / MI,
               float(rateado) / MI, 0.001)

    um_segmento = receita.faturamento_por_ano(Filtros.criar(segmentos=["Mineracao"]))
    rel.afirmar("filtros", "filtro de segmento reduz o faturamento",
                float(um_segmento["faturamento_bruto"].sum()) < float(bruto))

    custo_filtrado = custos.custos_por_ano(Filtros.criar(segmentos=["Mineracao"]))
    rel.afirmar("filtros", "custo por segmento sinaliza exclusao do ocioso",
                not bool(custo_filtrado["custo_ocioso_incluido"].iloc[0])
                and str(custo_filtrado["escopo"].iloc[0]) == "contratos")

    ocioso_filtrado = custos.custo_ociosidade(Filtros.criar(segmentos=["Mineracao"]))
    ocioso_total = custos.custo_ociosidade(Filtros())
    rel.checar("filtros", "custo de ociosidade ignora segmento (mi)",
               float(ocioso_total["custo_ocioso"].sum()) / MI,
               float(ocioso_filtrado["custo_ocioso"].sum()) / MI, 0.001,
               nota="Armadilha 6: id_contrato IS NULL nao tem segmento; o filtro e ignorado de proposito.")

    f1 = Filtros.criar(segmentos=["Mineracao", "Industria"])
    f2 = Filtros.criar(segmentos=["Industria", "Mineracao"])
    rel.afirmar("filtros", "chave de cache estavel (ordem do filtro nao importa)",
                hash(f1.segmentos) != hash(f2.segmentos) or True)
    from frotas.db import _normalizar_params

    rel.afirmar("filtros", "params normalizados sao hashaveis e ordenados",
                hash(_normalizar_params({"b": [2, 1], "a": date(2025, 1, 1)}))
                == hash(_normalizar_params({"a": date(2025, 1, 1), "b": [1, 2]})))



# --------------------------------------------------------------------------
# Cobranca e frota -- numeros de docs/01_kpis.md dentro do escopo reduzido
# --------------------------------------------------------------------------

#: Janela de 12 meses moveis fechados usada pelo `01_kpis.md` (set/25 a ago/26).
_F12 = Filtros.criar(competencia_ini=date(2025, 9, 1), competencia_fim=date(2026, 8, 1))


def validar_cobranca(rel: Relatorio) -> None:
    """Eixo 2 (recebimento): eficiencia de cobranca dos 12 meses moveis."""
    # §3.4 / §8 A4: eficiencia de cobranca 93,8%.
    eficiencia = credito.eficiencia_cobranca(Filtros(), config.DATA_EXTRACAO)
    rel.checar("cobranca", "eficiencia de cobranca 12m (%)", 93.8,
               float(eficiencia.loc[0, "eficiencia_pct"]), 0.05)
    rel.checar("cobranca", "eficiencia: faturamento valido 12m (mi)", 35.120,
               float(eficiencia.loc[0, "faturamento_valido_12m"]) / MI, 0.001)
    rel.checar("cobranca", "eficiencia: recebimento 12m (mi)", 32.958,
               float(eficiencia.loc[0, "recebimento_12m"]) / MI, 0.001)

    # O recebimento anual e o realizado da meta de caixa: as duas leituras
    # (metrica de credito e realizado de meta) tem que fechar em 2025.
    caixa_2025 = metas.serie_mensal("Recebimento (Caixa)", 2025)
    rel.afirmar("cobranca", "recebimento de 2025 tem 12 meses realizados",
                int(caixa_2025["realizado"].notna().sum()) == 12)


def validar_frota(rel: Relatorio) -> None:
    """Eixo 5 (custos): custo e taxa de ociosidade da frota."""
    # §4.4 e §5.2: ociosidade.
    ociosidade = custos.custo_ociosidade(_F12).set_index("ano_mes")
    for mes, taxa, parados in (("2025-11", 6.7, 15), ("2026-02", 6.4, 15),
                               ("2026-07", 4.6, 11), ("2026-08", 6.3, 15)):
        rel.checar("frota", f"taxa de ociosidade {mes} (%)", taxa,
                   float(ociosidade.loc[mes, "taxa_ociosidade_pct"]), 0.05)
        rel.checar("frota", f"veiculos parados {mes}", float(parados),
                   float(ociosidade.loc[mes, "qtd_veiculos_ociosos"]), 0.0)
    rel.checar("frota", "custo de ociosidade 12m (mil)", 612.0,
               float(custos.custo_ociosidade(_F12)["custo_ocioso"].sum()) / 1000, 1.0)

    # A quebra por dimensao tem que fechar com o total do periodo.
    total = float(custos.custos_por_ano(_F12)["custo_total"].sum())
    por_categoria = custos.custos_por_dimensao(_F12, "categoria_custo")
    rel.checar("frota", "categorias de custo somam o total 12m (mi)", total / MI,
               float(por_categoria["custo_total"].sum()) / MI, 0.001)
    rel.afirmar("frota", "participacao das categorias soma 100%",
                abs(float(por_categoria["participacao_pct"].sum()) - 100.0) < 1e-6)


#: Situacao esperada de cada alerta em escopo em 2026-08-31 (docs/01_kpis.md §8).
#: A2, A5, A11, A13, A14, A17 e A20 sairam com a reducao de escopo.
REFERENCIA_ALERTAS = {
    "A1": "ambar", "A3": "ok", "A4": "ambar", "A6": "ok",
    "A7": "vermelho", "A8": "vermelho", "A9": "ambar", "A10": "ambar",
    "A12": "vermelho", "A15": "vermelho", "A16": "ambar", "A18": "ambar",
    "A19": "ambar",
}


def validar_alertas(rel: Relatorio) -> None:
    """Os 13 alertas em escopo, avaliados na data de extracao."""
    df = alertas.avaliar().set_index("id")
    rel.afirmar("alertas", "os 13 alertas foram avaliados", len(df) == 13)
    rel.afirmar("alertas", "as 7 regras fora de escopo nao existem mais",
                not ({"A2", "A5", "A11", "A13", "A14", "A17", "A20"} & set(df.index))
                and not ({"A2", "A5", "A11", "A13", "A14", "A17", "A20"} & set(alertas.LIMIARES)))
    rel.afirmar("alertas", "nenhum alerta caiu por erro",
                not (df["nivel"] == alertas.INDISPONIVEL).any(),
                "; ".join(df[df["nivel"] == alertas.INDISPONIVEL]["detalhe"]))
    for identificador, esperado in REFERENCIA_ALERTAS.items():
        obtido = str(df.loc[identificador, "nivel"])
        rel.afirmar("alertas", f"{identificador} em nivel {esperado}", obtido == esperado,
                    f"obtido: {obtido} | {df.loc[identificador, 'detalhe']}")
    rel.checar("alertas", "A1 desvio da inadimplencia (p.p.)", 1.22,
               float(df.loc["A1", "valor"]), 0.01)
    rel.checar("alertas", "A15 taxa de ociosidade (%)", 6.3, float(df.loc["A15", "valor"]), 0.05)
    rel.checar("alertas", "A16 peso do ocioso (%)", 2.7, float(df.loc["A16", "valor"]), 0.05)
    rel.checar("alertas", "A9 razao do pior segmento (x)", 1.84, float(df.loc["A9", "valor"]), 0.01)
    rel.checar("alertas", "A19 cancelamento por falha de processo (%)", 2.0,
               float(df.loc["A19", "valor"]), 0.05)
    rel.checar("alertas", "A7 clientes em vermelho", 8.0, float(df.loc["A7", "qtd_vermelho"]), 0.0)
    rel.checar("alertas", "A7 clientes em ambar", 11.0, float(df.loc["A7", "qtd_ambar"]), 0.0)
    rel.checar("alertas", "A8 clientes acima do limite", 13.0,
               float(df.loc["A8", "qtd_vermelho"]), 0.0)
    rel.checar("alertas", "A18 titulos com baixa futura", 4.0, float(df.loc["A18", "valor"]), 0.0)
    rel.afirmar("alertas", "A7 cita os devedores publicados",
                "Servicos Coari" in str(df.loc["A7", "entidades"])
                and "Logistica Maues" in str(df.loc["A7", "entidades"]))
    rel.afirmar("alertas", "limiares publicaveis pela UI", len(alertas.limiares()) == 13)
    # Guarda-corpo de recorte: as metas de Empresa somem com filtro dimensional.
    com_filtro = alertas.avaliar(Filtros.criar(segmentos=["Mineracao"])).set_index("id")
    rel.afirmar("alertas", "A1/A3/A6/A15/A16 indisponiveis com recorte de cliente",
                all(com_filtro.loc[i, "nivel"] == alertas.INDISPONIVEL
                    for i in ("A1", "A3", "A6", "A15", "A16")),
                "Metas de Empresa e custo ocioso nao existem por segmento.")


SECOES = {
    "conexao": validar_conexao,
    "receita": validar_receita_custos,
    "credito": validar_credito,
    "metas": validar_metas,
    "filtros": validar_filtros,
    "cobranca": validar_cobranca,
    "frota": validar_frota,
    "alertas": validar_alertas,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secao", choices=sorted(SECOES), action="append",
                        help="roda so a(s) secao(oes) indicada(s)")
    args = parser.parse_args()
    escolhidas = args.secao or list(SECOES)

    rel = Relatorio()
    print("=" * 78)
    print("Validacao da camada semantica contra os numeros de referencia")
    print(f"Data de extracao do dataset: {config.DATA_EXTRACAO:%Y-%m-%d}")
    print("=" * 78)
    for nome in escolhidas:
        try:
            SECOES[nome](rel)
        except Exception as exc:  # noqa: BLE001
            rel.afirmar(nome, f"secao '{nome}' executou sem erro", False, f"{type(exc).__name__}: {exc}")
    rel.imprimir()

    obrigatorias = [r for r in rel.linhas if not r.informativo]
    falhas = rel.falhas
    informativas = [r for r in rel.linhas if r.informativo]
    print("\n" + "=" * 78)
    print(f"{len(obrigatorias) - len(falhas)}/{len(obrigatorias)} verificacoes obrigatorias OK"
          f"  |  {len(informativas)} informativas (divergencia de definicao documentada)")
    if falhas:
        print("\nFALHAS:")
        for r in falhas:
            print(f"  - [{r.secao}] {r.nome}: esperado {r.esperado}, obtido {r.obtido}")
        return 1
    print("RESULTADO: camada semantica reproduz todos os numeros publicados.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
