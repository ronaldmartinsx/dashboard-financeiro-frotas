"""Avaliador dos alertas de ``docs/01_kpis.md`` §8, no escopo reduzido do app.

**Sao 13 regras**, nao as 20 originais. Sairam com a reducao de escopo as sete
que dependiam de metricas que o projeto nao tem mais: **A2** e **A11** (serie
historica e sequencia de inadimplencia -- o eixo 3 e so a posicao atual),
**A5**, **A13**, **A17** e **A20** (margem operacional, margem por contrato) e
**A14** (manutencao corretiva recorrente). Restam
A1, A3, A4, A6, A7, A8, A9, A10, A12, A15, A16, A18 e A19 -- os identificadores
**nao** foram renumerados, para nao quebrar a rastreabilidade com o `01_kpis.md`.

**Por que isto vive na camada semantica e nao na view.** A UI sabe traduzir nivel
em cor; ela nao deve saber *quais* sao os limiares nem como avaliar a regra.
Duplicar isso em ``views/`` garantiria divergencia entre paginas. Aqui os limiares
sao um dicionario unico (:data:`LIMIARES`), publicavel na propria UI por
:func:`limiares`.

**Janelas.** Os filtros dimensionais de :class:`Filtros` sao respeitados, mas as
regras de 12 meses (A4, A16) usam **sempre** a janela movel de 12 meses que
termina em ``data_ref``, e as de meta (A1, A3, A6) usam o ano de ``data_ref``.
Deixar a tela mexer nessas janelas tornaria o alerta incomparavel com o limiar --
um alerta que muda de cor conforme o zoom nao e alerta.

**Custo.** :func:`avaliar` chama ~9 funcoes de metrica; todas sao cacheadas,
entao a partir da segunda pagina o banner e instantaneo. Chame uma vez por render
e reutilize o DataFrame nas paginas, filtrando por ``pagina``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable

import pandas as pd

from frotas.filtros import Filtros
# format.py e Python puro (sem Streamlit): os textos de alerta sao apresentacao e
# precisam sair em pt-BR. Ver a divida de camada registrada em docs/04_handover.md.
from frotas.ui import format as fmt
from frotas.metrics import credito, custos, metas, receita

#: Ordem de severidade, para consolidar e ordenar.
NIVEIS: tuple[str, ...] = ("ok", "ambar", "vermelho")

#: Nivel devolvido quando a regra nao pode ser avaliada no recorte atual.
INDISPONIVEL = "indisponivel"


@dataclass(frozen=True)
class Limiar:
    """Definicao de um alerta: onde aparece, o que mede e a partir de quando doi.

    Attributes:
        direcao: ``'maior_pior'`` (dispara acima do limiar) ou ``'menor_pior'``
            (dispara abaixo). ``'evento'`` = binario, sem escala numerica.
        ambar / vermelho: valores de corte na unidade da metrica. ``None`` quando
            aquele nivel nao existe para a regra.
    """

    id: str
    categoria: str
    pagina: int
    titulo: str
    unidade: str
    direcao: str
    ambar: float | None
    vermelho: float | None
    regra: str


LIMIARES: dict[str, Limiar] = {
    "A1": Limiar("A1", "empresa", 1, "Inadimplência acima da meta do mês", "p.p.",
                 "maior_pior", 1.0, 2.0,
                 "Inadimplência acima de 30 dias na data de referência, menos a meta vigente do mesmo mês."),
    "A3": Limiar("A3", "empresa", 1, "Faturamento abaixo da meta", "% da meta",
                 "menor_pior", 95.0, 90.0,
                 "Faturamento realizado do período dividido pela soma das metas mensais vigentes dos mesmos meses."),
    "A4": Limiar("A4", "empresa", 1, "Eficiência de cobrança", "%",
                 "menor_pior", 95.0, 93.0,
                 "Recebimento em caixa dos últimos 12 meses dividido pelo faturamento válido das mesmas 12 competências."),
    "A6": Limiar("A6", "empresa", 1, "Custo acima da meta do mês", "% da meta",
                 "maior_pior", 105.0, 110.0,
                 "Custo operacional do mês da data de referência dividido pela meta mensal vigente."),
    "A7": Limiar("A7", "credito", 3, "Clientes com vencido alto sobre a própria receita", "%",
                 "maior_pior", 10.0, 20.0,
                 "Por cliente: vencido há mais de 30 dias dividido pelo faturamento dos 12 meses do próprio cliente."),
    "A8": Limiar("A8", "credito", 3, "Clientes acima do limite de crédito", "%",
                 "maior_pior", 80.0, 100.0,
                 "Por cliente: carteira em aberto dividida pelo limite de crédito. Vermelho = bloquear novo faturamento."),
    "A9": Limiar("A9", "credito", 3, "Segmentos com inadimplência desproporcional", "x empresa",
                 "maior_pior", 1.5, 2.0,
                 "Inadimplência do segmento dividida pela inadimplência da empresa, ambas na data de referência."),
    "A10": Limiar("A10", "credito", 3, "Vencido há mais de 180 dias", "R$ por cliente",
                  "maior_pior", 0.01, 100_000.0,
                  "Por cliente: saldo vencido há mais de 180 dias. Âmbar com qualquer valor, vermelho a partir de R$ 100 mil."),
    "A12": Limiar("A12", "credito", 3, "Títulos a caminho da baixa (mais de 300 dias)", "títulos",
                  "evento", None, 1.0,
                  "Títulos não pagos e não cancelados com mais de 300 dias de vencimento: viram baixa aos 365."),
    "A15": Limiar("A15", "frota", 4, "Taxa de ociosidade da frota no mês", "%",
                  "maior_pior", 4.0, 6.0,
                  "Veículos sem contrato no mês da data de referência, sobre a frota com custo no mesmo mês."),
    "A16": Limiar("A16", "frota", 4, "Peso do custo de ociosidade", "%",
                  "maior_pior", 2.5, 4.0,
                  "Custo de veículo ocioso dos últimos 12 meses sobre o custo operacional dos mesmos 12 meses."),
    "A18": Limiar("A18", "qualidade", 0, "Títulos com baixa posterior à data de referência", "títulos",
                  "evento", 1.0, None,
                  "Títulos cuja data de baixa é posterior à foto: a baixa ainda não havia ocorrido na data de referência."),
    "A19": Limiar("A19", "qualidade", 0, "Cancelamento por falha de processo", "% do faturamento",
                  "maior_pior", 1.0, 3.0,
                  "Cancelamentos por Erro de Emissão e Faturamento Indevido sobre o faturamento do período."),
}


def limiares() -> pd.DataFrame:
    """Tabela dos limiares, para publicar na UI ou na documentacao.

    Colunas: ``id``, ``categoria``, ``pagina``, ``titulo``, ``unidade``,
    ``direcao``, ``ambar``, ``vermelho``, ``regra``.
    """
    return pd.DataFrame([vars(l) for l in LIMIARES.values()])


def _nivel(valor: float | None, lim: Limiar) -> str:
    """Traduz valor em nivel respeitando a direcao do limiar."""
    if valor is None or pd.isna(valor):
        return INDISPONIVEL
    valor = float(valor)
    if lim.direcao == "menor_pior":
        if lim.vermelho is not None and valor <= lim.vermelho:
            return "vermelho"
        if lim.ambar is not None and valor <= lim.ambar:
            return "ambar"
        return "ok"
    if lim.vermelho is not None and valor >= lim.vermelho:
        return "vermelho"
    if lim.ambar is not None and valor >= lim.ambar:
        return "ambar"
    return "ok"


def _pior(niveis: Iterable[str]) -> str:
    ordem = {INDISPONIVEL: -1, "ok": 0, "ambar": 1, "vermelho": 2}
    encontrados = [n for n in niveis]
    return max(encontrados, key=lambda n: ordem.get(n, -1)) if encontrados else "ok"


@dataclass
class _Contexto:
    """Frames compartilhados entre regras -- cada um custa uma consulta, cacheada."""

    filtros: Filtros
    ref: date

    def __post_init__(self) -> None:
        self.ano = self.ref.year
        self.ano_mes = f"{self.ref:%Y-%m}"
        # Janela movel de 12 meses de competencia terminando no mes da referencia.
        primeiro = date(self.ref.year, self.ref.month, 1)
        inicio = primeiro - pd.DateOffset(months=11)
        self.f12 = self.filtros.com(
            competencia_ini=date(inicio.year, inicio.month, 1),
            competencia_fim=primeiro,
            data_ref=self.ref,
        )
        self.f_foto = self.filtros.com(data_ref=self.ref)
        self._cache: dict[str, object] = {}

    def obter(self, chave: str, produtor: Callable[[], object]) -> object:
        if chave not in self._cache:
            self._cache[chave] = produtor()
        return self._cache[chave]

    # -- frames usados por mais de uma regra --------------------------------

    @property
    def comparativo(self) -> pd.DataFrame:
        return self.obter(  # type: ignore[return-value]
            "comparativo", lambda: metas.comparativo_anual(self.ano).set_index("tipo_meta")
        )

    @property
    def risco_clientes(self) -> pd.DataFrame:
        return self.obter(  # type: ignore[return-value]
            "risco_clientes",
            lambda: credito.risco_por_cliente(self.f_foto, self.ref, limite=None),
        )

    @property
    def aging_clientes(self) -> pd.DataFrame:
        return self.obter(  # type: ignore[return-value]
            "aging_clientes", lambda: credito.aging_por_cliente(self.f_foto, self.ref)
        )

    @property
    def ociosidade(self) -> pd.DataFrame:
        """Custo e taxa de ociosidade nos 12 meses moveis -- base de A15 e A16."""
        return self.obter(  # type: ignore[return-value]
            "ociosidade", lambda: custos.custo_ociosidade(self.f12)
        )


def _linha(
    lim: Limiar,
    nivel: str,
    valor: float | None,
    detalhe: str,
    qtd_vermelho: int = 0,
    qtd_ambar: int = 0,
    entidades: tuple[str, ...] = (),
) -> dict:
    return {
        "id": lim.id,
        "categoria": lim.categoria,
        "pagina": lim.pagina,
        "titulo": lim.titulo,
        "nivel": nivel,
        "valor": valor,
        "unidade": lim.unidade,
        "limiar_ambar": lim.ambar,
        "limiar_vermelho": lim.vermelho,
        "direcao": lim.direcao,
        "qtd_vermelho": qtd_vermelho,
        "qtd_ambar": qtd_ambar,
        "entidades": ", ".join(entidades),
        "detalhe": detalhe,
        "regra": lim.regra,
    }


def _por_entidade(
    lim: Limiar, df: pd.DataFrame, coluna_valor: str, coluna_nome: str,
    formatar: Callable[[float], str],
) -> dict:
    """Avalia uma regra que vale por linha (cliente, contrato, veiculo, segmento)."""
    if df.empty:
        return _linha(lim, "ok", None, "Nenhuma entidade no recorte atual.")
    # Colunas de percentual usam pd.NA (divisao por zero) e viram dtype object;
    # sem o to_numeric o nlargest quebra com TypeError.
    df = df.assign(**{coluna_valor: pd.to_numeric(df[coluna_valor], errors="coerce")})
    df = df[df[coluna_valor].notna()]
    if df.empty:
        return _linha(lim, "ok", None, "Nenhuma entidade com valor calculável no recorte.")
    serie = df[coluna_valor].astype(float)
    niveis = serie.map(lambda v: _nivel(v, lim))
    vermelhos = df[niveis == "vermelho"]
    ambares = df[niveis == "ambar"]
    pior = _pior(niveis.tolist())
    criticos = vermelhos if not vermelhos.empty else ambares
    if lim.direcao == "menor_pior":
        criticos = criticos.nsmallest(5, coluna_valor)
        extremo = serie.min()
    else:
        criticos = criticos.nlargest(5, coluna_valor)
        extremo = serie.max()
    nomes = tuple(
        f"{n} ({formatar(float(v))})"
        for n, v in zip(criticos[coluna_nome], criticos[coluna_valor])
    )
    detalhe = (
        f"{len(vermelhos)} em nível vermelho e {len(ambares)} em âmbar "
        f"de {len(df)} avaliados."
    )
    return _linha(lim, pior, float(extremo), detalhe, len(vermelhos), len(ambares), nomes)


# --------------------------------------------------------------------------
# Regras
# --------------------------------------------------------------------------


def _a1(ctx: _Contexto) -> dict:
    lim = LIMIARES["A1"]
    serie = metas.serie_mensal("Inadimplencia > 30d", ctx.ano).set_index("ano_mes")
    if ctx.ano_mes not in serie.index or ctx.filtros.tem_recorte_cliente:
        return _linha(lim, INDISPONIVEL, None,
                      "Inadimplência só tem meta no nível Empresa.")
    linha = serie.loc[ctx.ano_mes]
    realizado, meta = float(linha["realizado"]), float(linha["meta"])
    valor = realizado - meta
    return _linha(lim, _nivel(valor, lim), valor,
                  f"{fmt.competencia(ctx.ano_mes)}: realizado {fmt.percentual(realizado, 2)} "
                  f"contra meta de {fmt.percentual(meta, 2)}.")


def _a3(ctx: _Contexto) -> dict:
    lim = LIMIARES["A3"]
    if "Faturamento" not in ctx.comparativo.index or ctx.filtros.tem_recorte_cliente:
        return _linha(lim, INDISPONIVEL, None, "Sem meta comparável neste recorte.")
    linha = ctx.comparativo.loc["Faturamento"]
    meta = float(linha["meta_alinhada"])
    valor = 100.0 * float(linha["realizado"]) / meta if meta else float("nan")
    return _linha(lim, _nivel(valor, lim), valor,
                  f"{linha['periodo_realizado']}: realizado sobre a meta dos mesmos meses.")


def _a4(ctx: _Contexto) -> dict:
    lim = LIMIARES["A4"]
    df = credito.eficiencia_cobranca(ctx.f_foto, ctx.ref)
    valor = float(df.loc[0, "eficiencia_pct"])
    return _linha(lim, _nivel(valor, lim), valor,
                  f"12 meses até {fmt.competencia(ctx.ano_mes)}: "
                  f"{fmt.moeda_compacta(df.loc[0, 'recebimento_12m'])} recebidos sobre "
                  f"{fmt.moeda_compacta(df.loc[0, 'faturamento_valido_12m'])} faturados.")


def _a6(ctx: _Contexto) -> dict:
    lim = LIMIARES["A6"]
    if ctx.filtros.tem_recorte_cliente:
        return _linha(lim, INDISPONIVEL, None,
                      "Custo Operacional so tem meta no nivel Empresa (armadilha 6).")
    serie = metas.serie_mensal("Custo Operacional", ctx.ano).set_index("ano_mes")
    if ctx.ano_mes not in serie.index or pd.isna(serie.loc[ctx.ano_mes, "realizado"]):
        return _linha(lim, INDISPONIVEL, None, "Mes sem realizado.")
    linha = serie.loc[ctx.ano_mes]
    meta = float(linha["meta"])
    valor = 100.0 * float(linha["realizado"]) / meta if meta else float("nan")
    return _linha(lim, _nivel(valor, lim), valor,
                  f"{fmt.competencia(ctx.ano_mes)}: {fmt.moeda_compacta(float(linha['realizado']))} "
                  f"contra meta de {fmt.moeda_compacta(meta)}.")


def _a7(ctx: _Contexto) -> dict:
    return _por_entidade(LIMIARES["A7"], ctx.risco_clientes, "inadimplencia_pct",
                         "nome_cliente", lambda v: fmt.percentual(v, 1))


def _a8(ctx: _Contexto) -> dict:
    df = ctx.aging_clientes
    df = df[df["uso_limite_pct"].notna()] if not df.empty else df
    return _por_entidade(LIMIARES["A8"], df, "uso_limite_pct",
                         "nome_cliente", lambda v: fmt.percentual(v, 0))


def _a9(ctx: _Contexto) -> dict:
    lim = LIMIARES["A9"]
    empresa = float(
        credito.inadimplencia_ponto_no_tempo(ctx.f_foto, ctx.ref).loc[0, "inadimplencia_pct"]
    )
    df = credito.risco_por_segmento(ctx.f_foto, ctx.ref)
    if df.empty or not empresa:
        return _linha(lim, INDISPONIVEL, None, "Sem base para comparar.")
    df = df.assign(razao=df["inadimplencia_pct"] / empresa)
    linha = _por_entidade(lim, df, "razao", "segmento", fmt.vezes)
    linha["detalhe"] += f" Inadimplência da empresa: {fmt.percentual(empresa, 2)}."
    return linha


def _a10(ctx: _Contexto) -> dict:
    lim = LIMIARES["A10"]
    df = ctx.aging_clientes
    if df.empty or "180+d" not in df.columns:
        return _linha(lim, "ok", 0.0, "Nenhum saldo vencido há mais de 180 dias.")
    df = df[df["180+d"] > 0]
    if df.empty:
        return _linha(lim, "ok", 0.0, "Nenhum saldo vencido há mais de 180 dias.")
    linha = _por_entidade(lim, df, "180+d", "nome_cliente", lambda v: fmt.moeda(v, casas=0))
    linha["detalhe"] += f" Total vencido há mais de 180 dias: {fmt.moeda_compacta(df['180+d'].sum())}."
    return linha


def _a12(ctx: _Contexto) -> dict:
    lim = LIMIARES["A12"]
    titulos = credito.titulos_em_risco_de_baixa(ctx.f_foto, ctx.ref)
    if titulos.empty:
        return _linha(lim, "ok", 0.0, "Nenhum título com mais de 300 dias de vencimento.")
    total = float(titulos["valor_bruto"].sum())
    nomes = tuple(
        f"{n} ({fmt.moeda_compacta(v)})"
        for n, v in titulos.groupby("nome_cliente")["valor_bruto"].sum()
        .nlargest(5).items()
    )
    return _linha(lim, "vermelho", float(len(titulos)),
                  f"{len(titulos)} títulos, {fmt.moeda_compacta(total)}, viram baixa aos 365 dias.",
                  qtd_vermelho=len(titulos), entidades=nomes)


def _a15(ctx: _Contexto) -> dict:
    lim = LIMIARES["A15"]
    if ctx.filtros.tem_recorte_cliente:
        return _linha(lim, INDISPONIVEL, None,
                      "Veículo ocioso não tem cliente: métrica desabilitada com recorte de cliente.")
    df = ctx.ociosidade.set_index("ano_mes")
    if ctx.ano_mes not in df.index:
        return _linha(lim, INDISPONIVEL, None, "Mes sem custo registrado.")
    linha = df.loc[ctx.ano_mes]
    valor = float(linha["taxa_ociosidade_pct"])
    return _linha(lim, _nivel(valor, lim), valor,
                  f"{fmt.competencia(ctx.ano_mes)}: {int(linha['qtd_veiculos_ociosos'])} de "
                  f"{int(linha['qtd_veiculos_frota'])} veículos parados.")


def _a16(ctx: _Contexto) -> dict:
    lim = LIMIARES["A16"]
    if ctx.filtros.tem_recorte_cliente:
        return _linha(lim, INDISPONIVEL, None,
                      "Veículo ocioso não tem cliente: métrica desabilitada com recorte de cliente.")
    df = ctx.ociosidade
    ocioso, total = float(df["custo_ocioso"].sum()), float(df["custo_total"].sum())
    valor = 100.0 * ocioso / total if total else float("nan")
    return _linha(lim, _nivel(valor, lim), valor,
                  f"12 meses até {fmt.competencia(ctx.ano_mes)}: {fmt.moeda_compacta(ocioso)} de "
                  f"ociosidade sobre {fmt.moeda_compacta(total)} de custo.")


def _a18(ctx: _Contexto) -> dict:
    lim = LIMIARES["A18"]
    df = credito.titulos_com_baixa_futura(ctx.f_foto, ctx.ref)
    if df.empty:
        return _linha(lim, "ok", 0.0, "Nenhum título com baixa posterior à data de referência.")
    total = float(df["valor_bruto"].sum())
    return _linha(lim, "ambar", float(len(df)),
                  f"{len(df)} títulos, {fmt.moeda_compacta(total)}, com baixa registrada depois de "
                  f"{fmt.data_br(ctx.ref)}. A carteira em aberto os exclui; a inadimplência não.",
                  qtd_ambar=len(df))


def _a19(ctx: _Contexto) -> dict:
    lim = LIMIARES["A19"]
    motivos = receita._cancelamentos_por_motivo(ctx.filtros)
    if motivos.empty:
        return _linha(lim, "ok", 0.0, "Nenhum cancelamento no período.")
    falha = motivos[motivos["motivo_cancelamento"].isin(["Erro de Emissao", "Faturamento Indevido"])]
    valor = float(falha["pct_do_faturamento"].sum())
    return _linha(lim, _nivel(valor, lim), valor,
                  f"{fmt.moeda_compacta(float(falha['valor_bruto'].sum()))} cancelados por erro de "
                  "emissão ou faturamento indevido — falha de processo, não decisão comercial.",
                  entidades=tuple(falha["motivo_cancelamento"]))


_REGRAS: dict[str, Callable[[_Contexto], dict]] = {
    "A1": _a1, "A3": _a3, "A4": _a4, "A6": _a6, "A7": _a7, "A8": _a8, "A9": _a9,
    "A10": _a10, "A12": _a12, "A15": _a15, "A16": _a16, "A18": _a18, "A19": _a19,
}


def avaliar(
    filtros: Filtros | None = None,
    data_ref: date | None = None,
    ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Avalia os 13 alertas em escopo e devolve nivel e valores para o banner.

    Colunas: ``id``, ``categoria`` (empresa · credito · margem · frota ·
    qualidade), ``pagina`` (1, 3, 4, 5; 0 = barra de qualidade de dado em todas),
    ``titulo``, ``nivel`` (``ok`` · ``ambar`` · ``vermelho`` · ``indisponivel``),
    ``valor``, ``unidade``, ``limiar_ambar``, ``limiar_vermelho``, ``direcao``,
    ``qtd_vermelho``, ``qtd_ambar``, ``entidades``, ``detalhe``, ``regra``.

    A UI le ``nivel`` para a cor, ``titulo`` + ``detalhe`` para o texto e
    ``entidades`` para os nomes a citar. Nao precisa conhecer nenhum limiar --
    eles vem em ``limiar_ambar`` / ``limiar_vermelho`` caso queira desenhar a
    banda no grafico (é o que a serie de ociosidade faz em 4% e 6%).

    ``nivel = 'indisponivel'`` nao e falha: significa que a regra nao se aplica ao
    recorte -- tipicamente A1, A3 e A6 com filtro dimensional ativo (essas metas
    so existem no nivel Empresa) ou A15/A16 com recorte de cliente (custo de
    veiculo ocioso nao tem cliente). Renderize como cinza com o motivo em
    ``detalhe``, nunca como verde.

    Args:
        filtros: recorte da tela. Filtros dimensionais sao respeitados; as janelas
            temporais das regras **nao** (ver o docstring do modulo).
        data_ref: data da foto. Padrao: ``filtros.ref`` (2026-08-31).
        ids: subconjunto de alertas a avaliar (ex.: ``('A15', 'A16')`` na pagina
            de frota). Padrao: todos.

    Situacao em 2026-08-31, sem filtro, conferida pelo validador: **4 vermelhos**
    (A7 com 8 clientes, A8 com 13, A12, A15 com ociosidade de 6,3%), **7 ambar**
    (A1 +1,22 p.p., A4 93,8%, A9 Servicos Publicos 1,84x, A10, A16 2,7%, A18,
    A19 2,0%) e **2 ok** (A3, A6).
    """
    filtros = filtros or Filtros()
    ref = data_ref or filtros.ref
    ctx = _Contexto(filtros=filtros, ref=ref)
    escolhidos = list(ids) if ids else list(LIMIARES)
    linhas: list[dict] = []
    for identificador in escolhidos:
        if identificador not in _REGRAS:
            raise ValueError(f"alerta desconhecido: {identificador!r}. Use um de {list(LIMIARES)}.")
        try:
            linhas.append(_REGRAS[identificador](ctx))
        except Exception as exc:  # noqa: BLE001 - um alerta quebrado nao derruba o banner
            linhas.append(
                _linha(LIMIARES[identificador], INDISPONIVEL, None,
                       f"Nao foi possivel avaliar: {type(exc).__name__}.")
            )
    df = pd.DataFrame(linhas)
    ordem = {"vermelho": 0, "ambar": 1, "ok": 2, INDISPONIVEL: 3}
    df["_o"] = df["nivel"].map(ordem)
    df["_n"] = df["id"].str.lstrip("A").astype(int)
    return df.sort_values(["_o", "_n"]).drop(columns=["_o", "_n"]).reset_index(drop=True)


def resumo(filtros: Filtros | None = None, data_ref: date | None = None) -> dict:
    """Contagem por nivel, para o badge do cabecalho.

    Chaves: ``vermelho``, ``ambar``, ``ok``, ``indisponivel``, ``nivel_geral``.
    """
    df = avaliar(filtros, data_ref)
    contagem = df["nivel"].value_counts().to_dict()
    return {
        "vermelho": int(contagem.get("vermelho", 0)),
        "ambar": int(contagem.get("ambar", 0)),
        "ok": int(contagem.get("ok", 0)),
        "indisponivel": int(contagem.get(INDISPONIVEL, 0)),
        "nivel_geral": _pior([n for n in df["nivel"] if n != INDISPONIVEL]),
    }
