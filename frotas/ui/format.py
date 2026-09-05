"""Formatacao pt-BR do app. Sem ``locale``, sem Streamlit, sem pandas.

Por que nao ``locale``: ``locale.setlocale`` e global ao processo, depende de o
sistema ter ``pt_BR.UTF-8`` instalado e nao e thread-safe -- tres problemas num
app Streamlit. A separacao de milhar e a virgula decimal sao feitas na mao.

Convencoes fixadas aqui (a especificacao completa esta em ``docs/03_ux.md``
secao 3):

* separador de milhar ``.`` e decimal ``,``  -- ``R$ 1.234.567,89``;
* moeda compacta com sufixo minusculo -- ``R$ 3,19 mi``, ``R$ 655,0 mil``;
* percentual com **1 casa** em KPI e **2 casas** onde a comparacao com meta
  exige (``10,02%`` vs ``8,80%``);
* variacao de metrica **percentual** sai em **pontos percentuais** --
  ``+7,20 p.p.``, nunca ``+240%``;
* competencia como ``ago/26`` (eixo) ou ``ago/2026`` (titulo e tooltip);
* sinal negativo tipografico ``−`` (menos), nao hifen: alinha com o ``+`` na
  mesma largura e nao vira quebra de linha;
* ausencia de dado e ``—`` (travessao), **nunca** ``0``, ``nan`` ou ``None``.

Texto de interface sem acento, como o resto do projeto e como os dominios do
banco (``Construcao Civil``, ``Logistica e Transporte``): misturar
``Construcao`` do dado com ``março`` do rotulo fica pior do que abrir mao do
acento nos dois.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final, Literal

from frotas.ui import theme
from frotas.ui.theme import Direcao, Nivel, Tema

# --------------------------------------------------------------------------
# Constantes de estilo textual
# --------------------------------------------------------------------------

#: Placeholder de dado ausente. Um so, em todo o app.
VAZIO: Final[str] = "—"          # travessao

#: Sinal de menos tipografico (U+2212). Ver docstring do modulo.
MENOS: Final[str] = "−"
MAIS: Final[str] = "+"

MESES: Final[tuple[str, ...]] = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)

MESES_LONGOS: Final[tuple[str, ...]] = (
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

_ESCALAS: Final[tuple[tuple[float, str, int], ...]] = (
    (1e12, "tri", 2),
    (1e9, "bi", 2),
    (1e6, "mi", 2),
    (1e3, "mil", 1),
)

_RE_COMPETENCIA = re.compile(r"^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?")


# --------------------------------------------------------------------------
# Base numerica
# --------------------------------------------------------------------------


def eh_vazio(valor: Any) -> bool:
    """``True`` para ``None``, ``NaN``, ``pd.NA``, string vazia e infinito.

    Infinito entra na lista de proposito: divisao por zero na camada semantica
    (margem de contrato sem receita, por exemplo) chega aqui como ``inf``, e
    ``inf`` na tela e pior do que travessao.

    ``pd.NA`` e ``pd.NaT`` sao reconhecidos pelo **nome do tipo**, nao por
    ``isinstance``: este modulo nao importa pandas (ver docstring do modulo).
    Sem esse ramo, ``float(pd.NA)`` levanta ``TypeError``, o ``except`` abaixo
    responderia "nao e vazio" e o formatador seguinte quebraria a pagina inteira
    -- foi exatamente o que derrubava a tabela por veiculo da pagina 5.
    """
    if valor is None:
        return True
    if valor.__class__.__name__ in ("NAType", "NaTType"):
        return True
    if isinstance(valor, str):
        return not valor.strip()
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return False  # nao e numero: quem formata texto decide o que fazer
    return math.isnan(f) or math.isinf(f)


def _partes(valor: float, casas: int) -> tuple[str, str]:
    """Devolve ``(sinal, corpo)`` com milhar em ponto e decimal em virgula."""
    arredondado = round(abs(float(valor)), casas)
    # -0,004 com 2 casas vira 0,00: o sinal tem que sumir junto, senao a tela
    # mostra "−0,00", que nao existe.
    sinal = MENOS if (valor < 0 and arredondado != 0) else ""
    inteiro, _, decimal = f"{arredondado:.{casas}f}".partition(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    corpo = ".".join(grupos)
    if casas:
        corpo = f"{corpo},{decimal}"
    return sinal, corpo


def numero(valor: Any, casas: int = 0, *, com_sinal: bool = False, vazio: str = VAZIO) -> str:
    """Numero em padrao brasileiro. ``numero(1234567.891, 2)`` -> ``1.234.567,89``."""
    if eh_vazio(valor):
        return vazio
    sinal, corpo = _partes(float(valor), casas)
    # O sinal segue o valor **arredondado**: −0,004 com 1 casa e zero na tela,
    # e zero nao leva sinal nenhum (nem "+0,0%", nem "−0,0%").
    if com_sinal and not sinal and not _zerou(valor, casas):
        sinal = MAIS
    return f"{sinal}{corpo}"


def _zerou(valor: Any, casas: int) -> bool:
    """O valor desaparece no arredondamento para ``casas``?"""
    return round(abs(float(valor)), casas) == 0


def contagem(valor: Any, *, unidade: str | None = None, vazio: str = VAZIO) -> str:
    """Contagem inteira. ``contagem(3160)`` -> ``3.160``; com unidade, ``245 veiculos``."""
    if eh_vazio(valor):
        return vazio
    texto = numero(round(float(valor)), 0)
    return f"{texto} {unidade}" if unidade else texto


# --------------------------------------------------------------------------
# Moeda
# --------------------------------------------------------------------------


def moeda(valor: Any, casas: int = 2, *, com_sinal: bool = False, vazio: str = VAZIO) -> str:
    """Moeda cheia. ``moeda(1234567.89)`` -> ``R$ 1.234.567,89``.

    Use em **tabela e tooltip**, onde o usuario confere numero. Para tile de KPI
    e eixo, use :func:`moeda_compacta`.

    O sinal fica **antes** do ``R$`` (``−R$ 15.000,00``): assim uma coluna de
    valores alinha o cifrao, e o olho encontra o negativo na margem.
    """
    if eh_vazio(valor):
        return vazio
    sinal, corpo = _partes(float(valor), casas)
    if com_sinal and not sinal and not _zerou(valor, casas):
        sinal = MAIS
    return f"{sinal}R$ {corpo}"


def moeda_compacta(
    valor: Any,
    *,
    casas: int | None = None,
    com_sinal: bool = False,
    vazio: str = VAZIO,
) -> str:
    """Moeda abreviada. ``3_192_000`` -> ``R$ 3,19 mi``; ``655_000`` -> ``R$ 655,0 mil``.

    Casas por escala (padrao, sobrescrevivel por ``casas``): tri/bi/mi com 2,
    mil com 1, abaixo de mil com 2. Duas casas em milhoes porque a diferenca
    entre ``R$ 3,19 mi`` e ``R$ 3,2 mi`` e de R$ 10 mil -- material numa
    carteira vencida.

    Abaixo de R$ 1.000 nao abrevia: ``R$ 847,20``. Zero exato sai ``R$ 0``, sem
    casas, para nao competir visualmente com valores reais.
    """
    if eh_vazio(valor):
        return vazio
    v = float(valor)
    if v == 0:
        return "R$ 0"
    absoluto = abs(v)
    for corte, sufixo, padrao in _ESCALAS:
        if absoluto >= corte:
            n = casas if casas is not None else padrao
            sinal, corpo = _partes(v / corte, n)
            if com_sinal and not sinal:
                sinal = MAIS
            return f"{sinal}R$ {corpo} {sufixo}"
    return moeda(v, casas if casas is not None else 2, com_sinal=com_sinal)


# --------------------------------------------------------------------------
# Percentual e pontos percentuais
# --------------------------------------------------------------------------


def percentual(
    valor: Any,
    casas: int = 1,
    *,
    com_sinal: bool = False,
    vazio: str = VAZIO,
) -> str:
    """Percentual ja em escala de 0-100. ``percentual(10.204, 2)`` -> ``10,20%``.

    A camada semantica devolve percentuais **em pontos** (``inadimplencia_pct =
    10.204``, ``margem_pct = 34.66``), igual a tabela ``metas``. Nada aqui
    multiplica por 100 -- se o numero chegar como 0,1020 o erro e de quem chamou.
    """
    if eh_vazio(valor):
        return vazio
    return f"{numero(valor, casas, com_sinal=com_sinal)}%"


def pontos_percentuais(
    valor: Any,
    casas: int = 2,
    *,
    com_sinal: bool = True,
    vazio: str = VAZIO,
) -> str:
    """Variacao de metrica percentual, em **pontos percentuais**.

    ``pontos_percentuais(7.2)`` -> ``+7,20 p.p.``

    Esta e a regra mais violada do projeto: a inadimplencia de 2025 fechou em
    10,20% contra meta de 3,00%. A diferenca e ``+7,20 p.p.``, **nao** ``+240%``.
    Toda variacao de metrica ja expressa em % (margem, inadimplencia, taxa de
    ociosidade, eficiencia de cobranca) passa por aqui.
    """
    if eh_vazio(valor):
        return vazio
    return f"{numero(valor, casas, com_sinal=com_sinal)} p.p."


def variacao(valor: Any, casas: int = 1, *, vazio: str = VAZIO) -> str:
    """Variacao relativa de metrica em **BRL ou contagem**. ``+6,8%``.

    So para grandezas absolutas (faturamento, caixa, custo, quantidade). Para
    metrica que ja e percentual, use :func:`pontos_percentuais`.
    """
    if eh_vazio(valor):
        return vazio
    return f"{numero(valor, casas, com_sinal=True)}%"


def vezes(valor: Any, casas: int = 2, *, vazio: str = VAZIO) -> str:
    """Razao como multiplo. ``vezes(1.8)`` -> ``1,80x`` (alerta A9)."""
    if eh_vazio(valor):
        return vazio
    return f"{numero(valor, casas)}x"


def dias(valor: Any, *, vazio: str = VAZIO) -> str:
    """Prazo em dias. ``dias(92)`` -> ``92 dias``; ``dias(1)`` -> ``1 dia``."""
    if eh_vazio(valor):
        return vazio
    n = round(float(valor))
    return f"{numero(n, 0)} dia" if abs(n) == 1 else f"{numero(n, 0)} dias"


# --------------------------------------------------------------------------
# Datas e competencias
# --------------------------------------------------------------------------


def _para_data(valor: Any) -> date | None:
    """Aceita date, datetime, Timestamp, ``'2026-08'`` e ``'2026-08-01'``."""
    if eh_vazio(valor):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if hasattr(valor, "to_pydatetime"):          # pandas.Timestamp
        try:
            return valor.to_pydatetime().date()
        except Exception:
            return None
    if isinstance(valor, str):
        casamento = _RE_COMPETENCIA.match(valor.strip())
        if casamento:
            ano, mes, dia = casamento.groups()
            try:
                return date(int(ano), int(mes), int(dia or 1))
            except ValueError:
                return None
    return None


def competencia(valor: Any, *, longo: bool = False, vazio: str = VAZIO) -> str:
    """Competencia mensal. ``ago/26`` (eixo) ou ``ago/2026`` (titulo, tooltip).

    ``competencia('2026-08')`` -> ``ago/26``;
    ``competencia(date(2026, 8, 1), longo=True)`` -> ``ago/2026``.
    """
    d = _para_data(valor)
    if d is None:
        return vazio
    ano = f"{d.year}" if longo else f"{d.year % 100:02d}"
    return f"{MESES[d.month - 1]}/{ano}"


def competencia_extensa(valor: Any, *, vazio: str = VAZIO) -> str:
    """Competencia por extenso, para texto corrido. ``agosto de 2026``."""
    d = _para_data(valor)
    return vazio if d is None else f"{MESES_LONGOS[d.month - 1]} de {d.year}"


def data_br(valor: Any, *, vazio: str = VAZIO) -> str:
    """Data civil. ``data_br(date(2026, 8, 31))`` -> ``31/08/2026``."""
    d = _para_data(valor)
    return vazio if d is None else f"{d.day:02d}/{d.month:02d}/{d.year}"


def periodo(ini: Any, fim: Any, *, longo: bool = True, vazio: str = VAZIO) -> str:
    """Intervalo de competencia. ``set/2025 a ago/2026``.

    Todo card que compara com meta tem que mostrar **qual periodo da meta foi
    usado** (regra editorial de docs/01_kpis.md 9.2 -- os erros D2 e D3
    nasceram de comparar 8 meses com meta anual). Este e o texto padrao disso.
    """
    a, b = competencia(ini, longo=longo, vazio=vazio), competencia(fim, longo=longo, vazio=vazio)
    if a == vazio and b == vazio:
        return vazio
    return f"{a} a {b}"


# --------------------------------------------------------------------------
# Delta: texto + nivel + cor + icone, numa coisa so
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Delta:
    """Um desvio pronto para renderizar, com todos os canais ja resolvidos.

    Attributes:
        texto: ``+7,20 p.p.``, ``−2,7%``, ou ``—`` quando nao ha meta.
        nivel: chave de :data:`frotas.ui.theme.ICONE_NIVEL`.
        cor: hex ja no tema pedido.
        icone: glifo do nivel -- garante que a cor nunca viaje sozinha.
        rotulo: texto do nivel, para ``aria-label`` / ``title``.
        favoravel: ``True``/``False``/``None`` (sem meta ou direcao neutra).
    """

    texto: str
    nivel: Nivel
    cor: str
    icone: str
    rotulo: str
    favoravel: bool | None

    @property
    def acessivel(self) -> str:
        """Texto completo para leitor de tela: ``+7,20 p.p. (critico)``."""
        return f"{self.texto} ({self.rotulo})"


def delta(
    valor: Any,
    *,
    unidade: Literal["pp", "pct", "brl", "num"] = "pp",
    direcao: Direcao = "maior_melhor",
    ambar: float | None = None,
    vermelho: float | None = None,
    tema: Tema = "claro",
    casas: int | None = None,
    vazio: str = VAZIO,
) -> Delta:
    """Monta o :class:`Delta` de um desvio realizado-vs-meta.

    Args:
        valor: o desvio ja calculado (``variacao_abs`` em p.p., ou
            ``variacao_pct`` em %). ``None`` quando o recorte nao tem meta.
        unidade: ``"pp"`` pontos percentuais (metrica que ja e %),
            ``"pct"`` variacao relativa, ``"brl"`` diferenca em reais,
            ``"num"`` diferenca em contagem.
        direcao: direcao do KPI -- ver :data:`frotas.ui.theme.DIRECAO_KPI`.
        ambar / vermelho: limiares da secao 8 de ``docs/01_kpis.md``, em modulo.
            Sem eles, um desvio desfavoravel sai **neutro**, nunca vermelho.

    Exemplos:
        >>> delta(7.20, unidade="pp", direcao="menor_melhor",
        ...       ambar=1.0, vermelho=2.0).texto
        '+7,20 p.p.'
        >>> delta(None).texto
        '—'
    """
    nivel = theme.nivel_delta(valor, direcao=direcao, ambar=ambar, vermelho=vermelho)
    if eh_vazio(valor):
        texto = vazio
        favoravel: bool | None = None
    else:
        v = float(valor)
        if unidade == "pp":
            texto = pontos_percentuais(v, 2 if casas is None else casas)
        elif unidade == "pct":
            texto = variacao(v, 1 if casas is None else casas)
        elif unidade == "brl":
            texto = moeda_compacta(v, com_sinal=True, casas=casas)
        else:
            texto = numero(v, 0 if casas is None else casas, com_sinal=True)
        if direcao == "neutro" or v == 0:
            favoravel = None
        else:
            favoravel = (v > 0) if direcao == "maior_melhor" else (v < 0)
    return Delta(
        texto=texto,
        nivel=nivel,
        cor=theme.cor_nivel(nivel, tema, uso="texto"),
        icone=theme.ICONE_NIVEL[nivel],
        rotulo=theme.ROTULO_NIVEL[nivel],
        favoravel=favoravel,
    )


# --------------------------------------------------------------------------
# Rotulos de eixo
# --------------------------------------------------------------------------


def eixo_moeda(valor: Any) -> str:
    """Tick de eixo em reais, curto e sem cifrao repetido: ``3,2 mi``, ``800 mil``."""
    if eh_vazio(valor):
        return ""
    v = float(valor)
    if v == 0:
        return "0"
    absoluto = abs(v)
    for corte, sufixo, _ in _ESCALAS:
        if absoluto >= corte:
            sinal, corpo = _partes(v / corte, 1)
            return f"{sinal}{corpo} {sufixo}"
    sinal, corpo = _partes(v, 0)
    return f"{sinal}{corpo}"


def eixo_percentual(valor: Any) -> str:
    """Tick de eixo em percentual, sempre sem casa decimal: ``10%``."""
    return "" if eh_vazio(valor) else percentual(valor, 0)


__all__ = [
    "VAZIO", "MENOS", "MAIS", "MESES", "MESES_LONGOS",
    "eh_vazio", "numero", "contagem",
    "moeda", "moeda_compacta",
    "percentual", "pontos_percentuais", "variacao", "vezes", "dias",
    "competencia", "competencia_extensa", "data_br", "periodo",
    "Delta", "delta", "eixo_moeda", "eixo_percentual",
]
