"""Tokens de cor, paletas nomeadas e regras de cor por status.

Este modulo e a fonte de verdade visual do app. Nada aqui importa Streamlit: e
so dado e funcao pura, para poder ser testado num script e reaproveitado por
Plotly, Altair, HTML de componente e pelo ``.streamlit/config.toml``.

De onde vem a paleta
--------------------
Da **camada de dados do Bancada**, o design system do portfolio do dono
(``tokens/dados.css``, ``entrega/dados/GUIA.md``). A tese do sistema e "a
bancada e escura, os artefatos sao claros": um dashboard construido na camada
clara **e** o artefato que o site escuro enquadra, e a captura dele entra numa
moldura do portfolio sem tratamento, porque o fundo dela ja e ``--papel``
(``#F4F6F8``).

A licenca cromatica que o sistema abre aqui, e so aqui: no portfolio matiz nao
carrega hierarquia; num dashboard carrega, porque matiz e o que codifica serie,
ordem e desvio. Vale **dentro de grafico, tabela e KPI**; fora disso o painel
segue acromatico.

O que o Bancada entrega pronto e por que cada peca serve:

* **6 matizes categoricos** no eixo azul-laranja, que a deuteranopia e a
  protanopia preservam, sobre escada de luminancia monotonica (L* 32 -> 74).
  Se o matiz colapsar, a ordem sobrevive pela luminancia.
* **dois neutros de referencia** (``#9AA8B4`` e ``#B9C4CD``) reservados para
  meta, orcado e ano anterior -- nunca um dos seis. E exatamente o que a linha
  de meta deste app precisava.
* **tres sinais recalibrados para fundo claro**, com contraste declarado. Os
  sinais do tema escuro nao sobrevivem aqui (o verde cai de 9,9:1 para 1,7:1).
* **escala divergente teal-terracota**, e nao verde-vermelho, que colapsa em
  deuteranopia justamente onde o dado importa.

Um tema so
----------
O app e claro por tese, nao por preferencia: ele **e** o artefato. O tema
escuro saiu; ``Tema`` continua existindo como parametro das funcoes publicas
para nao quebrar as chamadas, mas resolve sempre para :data:`TEMA_CLARO`.

Direcao da metrica
------------------
Metade dos KPIs melhora subindo (faturamento, caixa) e metade melhora descendo
(inadimplencia, custo, carteira vencida). Por isso **nenhuma funcao daqui pinta
um numero pelo sinal**: pinta por *favorabilidade*, que depende de
:data:`DIRECAO_KPI`. E o que impede o erro classico de mostrar em verde uma
inadimplencia que subiu -- e e a razao de os glifos deste app dizerem qualidade
(``✓ ! !! ✕``) e nao direcao (``▲ ▼``), diferente do Bancada, que so precisa do
delta simples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Tema = Literal["claro", "escuro"]
Nivel = Literal["bom", "atencao", "serio", "critico", "neutro", "meta"]
Direcao = Literal["maior_melhor", "menor_melhor", "neutro"]


# --------------------------------------------------------------------------
# 1. Superficies, tinta e chrome
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Tokens:
    """Todos os tokens de um tema. Frozen: tema nao muda em tempo de execucao."""

    nome: Tema

    # superficies
    plano: str            # fundo da pagina
    superficie: str       # fundo de card / area de grafico
    superficie_alta: str  # fundo de elemento sobreposto (tooltip, popover)
    superficie_fraca: str # faixa zebrada de tabela, estado desabilitado

    # tinta
    tinta: str            # texto primario
    tinta_secundaria: str # rotulo, subtitulo
    tinta_fraca: str      # eixo, legenda, texto de proveniencia

    # chrome de grafico
    grade: str            # linha de grade (fio de cabelo)
    eixo: str             # linha de base / eixo
    borda: str            # anel de 1px em card e marca sobreposta

    # status como cor de marca (preenchimento, ponto, faixa)
    marca_bom: str
    marca_atencao: str
    marca_serio: str
    marca_critico: str
    marca_neutro: str
    marca_meta: str       # linha/alvo de meta -- sempre tracejada, nunca solida

    # status como cor de texto (respeita 4,5:1 de WCAG)
    texto_bom: str
    texto_atencao: str
    texto_serio: str
    texto_critico: str
    texto_neutro: str


#: O tema. Superficie de card ``#F4F6F8`` -- o ``--papel`` do Bancada promovido
#: a ambiente inteiro. E contra ela que todo contraste deste arquivo foi medido.
#:
#: As tres cores de sinal vem dos valores **claros** do Bancada
#: (``--claro-sinal-*``), que sao seguros para texto (5,2 a 7,5:1). Por isso
#: ``marca_*`` e ``texto_*`` compartilham o valor em bom, atencao e critico --
#: no tema antigo eles divergiam porque o ambar de marca ficava em 1,77:1.
#:
#: ``serio`` e o unico valor **derivado**: o Bancada tem tres sinais e este app
#: tem quatro degraus de severidade. E o ponto medio entre atencao e critico,
#: conferido pelo piso de contraste em ``scripts/verificar_tema.py``.
#:
#: Os dois neutros sao o par que o Bancada reserva para referencia: ``marca_meta``
#: leva ``--dado-referencia``, que e o token designado para meta e orcado.
TEMA_CLARO: Final[Tokens] = Tokens(
    nome="claro",
    plano="#E6EBEF",            # --claro-canvas: mais escuro que o cartao, de proposito
    superficie="#F4F6F8",       # --claro-superficie (--papel)
    superficie_alta="#FBFCFD",  # --claro-elevada
    superficie_fraca="#DDE3E8", # --claro-afundada
    tinta="#101A24",            # --claro-titulo      16,2:1
    tinta_secundaria="#2B3A47", # --claro-corpo        9,8:1
    tinta_fraca="#5B6B78",      # --claro-secundario   4,7:1
    grade="#DDE4EA",            # --claro-grade
    eixo="#7C8B98",             # --claro-fio-controle 3,1:1 (WCAG 1.4.11)
    borda="#CCD6DE",            # --claro-fio
    marca_bom="#1D6F5C",        # --claro-sinal-positivo 5,2:1
    marca_atencao="#8A5A00",    # --claro-sinal-atencao  6,2:1
    marca_serio="#99460E",      # derivado (ver acima)
    marca_critico="#A8321C",    # --claro-sinal-negativo 7,5:1
    marca_neutro="#7C8B98",     # --claro-fio-controle: neutro solido o bastante para barra
    marca_meta="#9AA8B4",       # --dado-referencia: meta, orcado, ano anterior
    texto_bom="#1D6F5C",
    texto_atencao="#8A5A00",
    texto_serio="#99460E",
    texto_critico="#A8321C",
    texto_neutro="#5B6B78",     # --claro-secundario
)


def tokens(tema: Tema = "claro") -> Tokens:
    """Os tokens do app.

    ``tema`` continua na assinatura porque as views o passam, mas ha um tema so:
    o app **e** o artefato claro que o portfolio enquadra. Ver o topo do modulo.
    """
    return TEMA_CLARO


# --------------------------------------------------------------------------
# 2. Paleta categorica -- os seis matizes do Bancada
# --------------------------------------------------------------------------

#: Os seis matizes categoricos do Bancada (``--dado-1`` a ``--dado-6``), na ordem
#: publicada. **A ordem e escada de luminancia** (L* 32 -> 74, passo ~8) sobre o
#: eixo azul-laranja, que a deuteranopia e a protanopia preservam: se o matiz
#: colapsar, a ordem sobrevive pela luz. Nao reordene.
#:
#: Escolher um slot **por significado** (e o que :data:`INDICADORES` faz) e o uso
#: previsto; o que a regra proibe e embaralhar a sequencia por gosto.
PALETA_DADOS: Final[tuple[str, ...]] = (
    "#1C4468",  # 0 prussia saturado  L* 32
    "#A04A34",  # 1 terracota         L* 42
    "#6A5F9C",  # 2 violeta           L* 50
    "#3D8E94",  # 3 teal              L* 58
    "#D99442",  # 4 ambar             L* 66
    "#8FB3CC",  # 5 azul palido       L* 74
)

#: Matizes cujo contraste fica abaixo de 3:1 sobre ``superficie``. Onde eles
#: aparecem, a UI **tem** que oferecer rotulo direto ou a visao de tabela (regra
#: de alivio). Os valores saem medidos de ``scripts/verificar_tema.py``, que
#: falha se esta lista divergir da medicao.
_BAIXO_CONTRASTE: Final[frozenset[str]] = frozenset({"#D99442", "#8FB3CC"})

#: Cor de qualquer categoria fora do dominio conhecido ("Outros", nulo, resto do
#: Pareto). Nunca gerar um 7o matiz: dobre no neutro de projecao do Bancada.
COR_OUTROS: Final[str] = "#B9C4CD"

#: Preenchimento nulo -- a marca so tem contorno (barra fantasma do ano anterior,
#: por exemplo). Existe como token para que nenhuma view escreva cor na mao.
TRANSPARENTE: Final[str] = "rgba(0,0,0,0)"


#: Indicador orcado -> slot de :data:`PALETA_DADOS`. Cor **por indicador**: o
#: indicador atravessa as quatro paginas (card, serie e matriz), entao quem le
#: associa o matiz ao assunto em qualquer tela.
#:
#: Cada escolha preserva a relacao que o app ja tinha, so que na paleta do
#: Bancada. Nenhum indicador recebe a cor de um **sinal** (``marca_bom`` ou
#: ``marca_critico``): serie e status sao coisas diferentes e nao podem se
#: confundir na mesma tela.
#:
#: A inadimplencia e o caso delicado: terracota le como risco, que **e** o
#: significado, e o dono pediu para manter a associacao -- mas e um matiz de
#: serie (``--dado-2``), distinto do vermelho de alerta critico (``#A8321C``).
#: Um badge e uma barra na mesma tela continuam distinguiveis.
INDICADORES: Final[tuple[tuple[str, int], ...]] = (
    ("Faturamento", 0),          # prussia -- a serie que abre a leitura, o matiz ancora
    ("Receita Liquida", 5),      # azul palido -- parente do prussia: faturamento menos impostos
    ("Recebimento (Caixa)", 3),  # teal -- o dinheiro que entrou
    ("Custo Operacional", 4),    # ambar -- a saida
    ("Inadimplencia > 30d", 1),  # terracota -- ver acima
)


#: Rating de credito -> nivel de status. Rating **e** uma escala de risco, entao
#: reusar as cores de status e a leitura correta: A esta bom, D e critico. Nao ha
#: competicao com o alerta -- os dois falam da mesma coisa, saude do cliente.
RATING_NIVEL: Final[dict[str, Nivel]] = {
    "A": "bom",
    "B": "neutro",
    "C": "atencao",
    "D": "critico",
}


def cor_rating(nota: str, tema: Tema = "claro") -> str:
    """Cor de um rating de credito (A a D). Desconhecido cai em neutro."""
    return cor_nivel(RATING_NIVEL.get(str(nota).strip().upper(), "neutro"), tema)


def cor_indicador(indicador: str, tema: Tema = "claro") -> str:
    """Cor fixa de um indicador orcado, estavel em todas as paginas.

    Indicador desconhecido cai no slot 0 -- nunca gera matiz novo.
    """
    for nome, slot in INDICADORES:
        if nome == indicador:
            return PALETA_DADOS[slot]
    return PALETA_DADOS[0]


def paleta_categorica(tema: Tema = "claro") -> list[str]:
    """Os seis matizes categoricos, na ordem publicada pelo Bancada.

    Passe a lista inteira para o grafico (``colorway`` no Plotly,
    ``color_discrete_map`` quando houver dominio). Nunca deixe a biblioteca
    ciclar cores sozinha: um filtro que remove uma serie nao pode repintar as
    que sobraram.

    Acima de tres series, cor nao basta -- some traco, marcador ou, melhor,
    rotulo direto na serie (``views._comum.rotulos_de_barra``).
    """
    return list(PALETA_DADOS)


def exige_rotulo_direto(cor: str, tema: Tema = "claro") -> bool:
    """A cor fica abaixo de 3:1 na superficie e precisa de rotulo/tabela?"""
    return cor.upper() in _BAIXO_CONTRASTE


# --------------------------------------------------------------------------
# 3. Rampas sequenciais -- magnitude
# --------------------------------------------------------------------------

def _mistura(de: str, para: str, fracao: float) -> str:
    """Interpola dois hex em RGB. Deterministico e sem dependencia."""
    a = tuple(int(de[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(para[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * fracao):02X}" for x, y in zip(a, b))


def _expandir(ancoras: tuple[str, ...], passos: int) -> tuple[str, ...]:
    """Espalha ``ancoras`` em ``passos`` cores, interpolando entre vizinhas.

    As ancoras sao os valores publicados; os passos entre elas existem so para a
    rampa ter resolucao quando um grafico pede mais faixas do que o sistema
    publica. Sem isto, pedir 6 faixas de uma rampa de 5 devolvia **cor repetida**
    -- duas faixas de aging saiam identicas, que e um defeito de leitura.
    """
    if passos <= len(ancoras):
        return ancoras
    saida = []
    for i in range(passos):
        pos = i * (len(ancoras) - 1) / (passos - 1)
        base = min(int(pos), len(ancoras) - 2)
        saida.append(_mistura(ancoras[base], ancoras[base + 1], pos - base))
    return tuple(saida)


#: Ancoras da rampa neutra -- a sequencial do Bancada (``--dado-seq-1..5``), um
#: matiz so, terminando em ``--dado-1``. Claro = pouco, escuro = muito. Use para
#: grandeza **sem polaridade**: faturamento, custo, carteira.
_ANCORAS_NEUTRA: Final[tuple[str, ...]] = (
    "#E2EBF2", "#B3CADB", "#7BA4C1", "#43759B", "#1C4468",
)

#: Ancoras da rampa de risco -- a familia terracota do Bancada. Use **so** para
#: grandeza que e risco: inadimplencia, vencido, atraso. Fora disso use a neutra;
#: terracota nao e decoracao.
#:
#: Tres das cinco sao valores literais do sistema (``--dado-div-neg-1``,
#: ``--dado-2``, ``--dado-div-neg-2``); as duas mais claras sao interpoladas,
#: porque o Bancada nao publica uma sequencial terracota. Fica registrado aqui
#: para ninguem confundir com token oficial.
_ANCORAS_RISCO: Final[tuple[str, ...]] = (
    "#F0E2DC", "#DCBBAB", "#C98A72", "#A04A34", "#8F3B26",
)

#: Dez passos: nove sobram depois do piso ordinal, que e o maximo que
#: :func:`rampa` aceita. Assim nenhuma chamada devolve cor repetida.
RAMPA_NEUTRA: Final[tuple[str, ...]] = _expandir(_ANCORAS_NEUTRA, 10)
RAMPA_RISCO: Final[tuple[str, ...]] = _expandir(_ANCORAS_RISCO, 10)

#: Indice do primeiro passo utilizavel numa rampa **ordinal** (celulas discretas,
#: faixas de aging): os passos mais claros que isto nao alcancam 2:1 contra a
#: superficie e sumiriam como celula. Em preenchimento continuo a rampa inteira
#: vale, porque ali a vizinhanca da a leitura.
_PISO_ORDINAL: Final[dict[str, int]] = {"neutra": 1, "risco": 1}

_RAMPAS: Final[dict[str, tuple[str, ...]]] = {
    "neutra": RAMPA_NEUTRA,
    "risco": RAMPA_RISCO,
}


def rampa(
    nome: Literal["neutra", "risco"] = "neutra",
    tema: Tema = "claro",
    n: int = 5,
    *,
    ordinal: bool = True,
) -> list[str]:
    """Devolve ``n`` passos de uma rampa sequencial, do menor ao maior valor.

    Args:
        nome: ``"neutra"`` (grandeza sem polaridade) ou ``"risco"`` (so risco
            real).
        tema: aceito para compatibilidade de chamada; ha um tema so.
        n: quantos passos (2 a 9). Acima de 5 os passos se repetem, porque a
            sequencial do Bancada tem cinco.
        ordinal: ``True`` para marcas discretas -- respeita o piso de contraste
            do passo mais proximo da superficie. ``False`` libera a rampa
            inteira, para preenchimento continuo.

    Returns:
        Lista de hex na ordem "menor valor -> maior valor".
    """
    if nome not in _RAMPAS:
        raise ValueError(f"rampa desconhecida: {nome!r}. Use 'neutra' ou 'risco'.")
    n = max(2, min(9, int(n)))
    passos = list(_RAMPAS[nome])
    if ordinal:
        passos = passos[_PISO_ORDINAL[nome]:]
    return [passos[round(i * (len(passos) - 1) / (n - 1))] for i in range(n)]


# --------------------------------------------------------------------------
# 4. Escala divergente -- desvio favoravel x desfavoravel
# --------------------------------------------------------------------------
#
# ATENCAO: a escala divergente codifica **favorabilidade**, nao o sinal bruto.
# +7,20 p.p. de inadimplencia e o pior numero do dataset e tem que sair no polo
# desfavoravel, ainda que o numero seja positivo. Quem decide isso e
# DIRECAO_KPI, via posicao_divergente().

#: Polo desfavoravel (terracota) -> neutro -> polo favoravel (teal). E o par
#: divergente do Bancada, e a razao dele nao ser verde-vermelho esta escrita no
#: proprio sistema: esse par colapsa em deuteranopia justamente onde o dado
#: importa mais. Neutro claro no meio de proposito: no meio a leitura tem que
#: ser "nada acontecendo".
#:
#: Sao **sete** passos e nao os cinco do Bancada: os tres valores centrais de
#: cada lado sao literais do sistema (``--dado-div-*``) e os dois intermediarios
#: sao interpolados, para a escala ter resolucao suficiente no heatmap de desvio.
ESCALA_DIVERGENTE: Final[tuple[str, ...]] = (
    "#8F3B26",  # 0 --dado-div-neg-2  mais desfavoravel
    "#B06A50",  # 1 interpolado
    "#C98A72",  # 2 --dado-div-neg-1
    "#EDF0F3",  # 3 --dado-div-centro
    "#86B5BA",  # 4 --dado-div-pos-1
    "#55919B",  # 5 interpolado
    "#226E77",  # 6 --dado-div-pos-2  mais favoravel
)

#: Indices nomeados da escala. Existiam como literais (``escala[5]``,
#: ``escala[1]``) dentro da pagina de metas, o que quebraria em silencio se a
#: escala mudasse de tamanho -- e ela acabou de mudar.
IDX_DIVERGENTE_FAVORAVEL: Final[int] = 5
IDX_DIVERGENTE_DESFAVORAVEL: Final[int] = 1


def escala_divergente(tema: Tema = "claro") -> list[str]:
    """Sete passos: 3 desfavoraveis, neutro, 3 favoraveis."""
    return list(ESCALA_DIVERGENTE)


# --------------------------------------------------------------------------
# 5. Direcao dos KPIs e traducao limiar -> nivel -> cor
# --------------------------------------------------------------------------

#: Direcao de cada KPI. Chave = nome curto usado nos componentes de UI.
#: Fonte: docs/01_kpis.md secao 5.1 (coluna "Direcao").
DIRECAO_KPI: Final[dict[str, Direcao]] = {
    "faturamento_bruto": "maior_melhor",
    "receita_liquida": "maior_melhor",
    "recebimento_caixa": "maior_melhor",
    "margem_operacional": "maior_melhor",
    "cobertura_caixa": "maior_melhor",
    "recuperacao_vencidos": "maior_melhor",
    "mrr_contratado": "maior_melhor",
    "custo_operacional": "menor_melhor",
    "impostos": "menor_melhor",
    "inadimplencia_30d": "menor_melhor",
    "carteira_vencida": "menor_melhor",
    "custo_ociosidade": "menor_melhor",
    "taxa_ociosidade": "menor_melhor",
    "atraso_medio": "menor_melhor",
    "uso_limite_credito": "menor_melhor",
    "pct_cancelado": "menor_melhor",
    "ticket_medio": "neutro",
    "mix_receita": "neutro",
}

#: Glifo que acompanha cada nivel. Cor **nunca** viaja sozinha (acessibilidade).
#: Sao glifos tipograficos, nao emoji: renderizam em qualquer fonte de sistema.
#: Os glifos dizem **qualidade**, nunca direcao: quem informa se o numero subiu
#: ou desceu e o sinal do proprio numero. Por isso "bom" nao e um triangulo para
#: cima -- em "▲ −2,1%" (custo abaixo da meta, o que e bom) a seta parecia
#: contradizer o menos.
ICONE_NIVEL: Final[dict[Nivel, str]] = {
    "bom": "✓",       # visto -- "dentro do esperado"
    "atencao": "!",   # exclamacao -- "olhe isto"
    "serio": "!!",    # exclamacao dupla -- "olhe agora"
    "critico": "✕",   # xis -- "fora do aceitavel"
    "neutro": "–",    # travessao -- sem sinal (nao vai a tela: ver format.delta)
    "meta": "┄",      # tracejado -- alvo
}

#: Rotulo textual do nivel, para leitor de tela e para o ``title`` do elemento.
#: Rotulo de cada nivel. Estes textos vao para a **tela** (banner) e para o
#: aria-label, entao sao escritos em pt-BR com acento -- as chaves continuam sem,
#: porque sao identificadores internos.
ROTULO_NIVEL: Final[dict[Nivel, str]] = {
    "bom": "dentro da meta",
    "atencao": "atenção",
    "serio": "atenção alta",
    "critico": "crítico",
    "neutro": "sem sinal",
    "meta": "meta",
}


def nivel_por_limiar(
    valor: float | None,
    *,
    ambar: float | None = None,
    vermelho: float | None = None,
    direcao: Direcao = "menor_melhor",
) -> Nivel:
    """Classifica um valor contra os limiares da secao 8 de ``docs/01_kpis.md``.

    Args:
        valor: o numero apurado (ex.: 6.3 para taxa de ociosidade de 6,3%).
        ambar / vermelho: limiares na mesma unidade do valor. ``None`` desliga
            aquele nivel.
        direcao: ``"menor_melhor"`` dispara quando ``valor >= limiar``;
            ``"maior_melhor"`` dispara quando ``valor <= limiar``.

    Returns:
        ``"critico"``, ``"atencao"``, ``"bom"`` ou ``"neutro"`` (valor ausente
        ou nenhum limiar configurado).

    Exemplos:
        >>> nivel_por_limiar(6.3, ambar=4.0, vermelho=6.0)          # A15
        'critico'
        >>> nivel_por_limiar(93.8, ambar=95.0, vermelho=93.0,
        ...                  direcao="maior_melhor")                # A4
        'atencao'
    """
    if valor is None or valor != valor:  # NaN
        return "neutro"
    if ambar is None and vermelho is None:
        return "neutro"
    if direcao == "maior_melhor":
        atingiu = lambda limiar: valor <= limiar  # noqa: E731
    else:
        atingiu = lambda limiar: valor >= limiar  # noqa: E731
    if vermelho is not None and atingiu(vermelho):
        return "critico"
    if ambar is not None and atingiu(ambar):
        return "atencao"
    return "bom"


def nivel_delta(
    delta: float | None,
    *,
    direcao: Direcao = "maior_melhor",
    ambar: float | None = None,
    vermelho: float | None = None,
) -> Nivel:
    """Nivel de um desvio realizado-vs-meta, respeitando a direcao do KPI.

    Regra editorial (docs/01_kpis.md secao 9.2): **verde so para desvio
    favoravel confirmado**; vermelho **so** quando o limiar vermelho da secao 8
    foi atingido. Desvio desfavoravel sem limiar configurado sai neutro -- e nao
    vermelho -- porque a UI nao pode inventar severidade.

    Exemplos:
        >>> nivel_delta(+7.20, direcao="menor_melhor", ambar=1.0, vermelho=2.0)
        'critico'
        >>> nivel_delta(+2.92, direcao="maior_melhor")
        'bom'
        >>> nivel_delta(None)
        'neutro'
    """
    if delta is None or delta != delta:
        return "neutro"
    if direcao == "neutro" or delta == 0:
        return "neutro"
    favoravel = (delta > 0) if direcao == "maior_melhor" else (delta < 0)
    if favoravel:
        return "bom"
    magnitude = abs(delta)
    if vermelho is not None and magnitude >= abs(vermelho):
        return "critico"
    if ambar is not None and magnitude >= abs(ambar):
        return "atencao"
    return "neutro"


def cor_nivel(nivel: Nivel, tema: Tema = "claro", uso: Literal["marca", "texto"] = "marca") -> str:
    """Cor de um nivel de status.

    ``uso="marca"`` para preenchimento, ponto, faixa e borda (piso 3:1);
    ``uso="texto"`` para numero e rotulo (piso 4,5:1 de WCAG). No tema claro o
    ambar de marca (#FAB219) fica em 1,77:1 -- **por isso** ele nunca aparece
    sozinho: sempre com o glifo de :data:`ICONE_NIVEL` e o rotulo de
    :data:`ROTULO_NIVEL`.
    """
    t = tokens(tema)
    campo = ("marca_" if uso == "marca" else "texto_") + (
        "neutro" if nivel == "meta" and uso == "texto" else nivel
    )
    return getattr(t, campo, t.marca_neutro if uso == "marca" else t.texto_neutro)


def cor_delta(
    delta: float | None,
    *,
    direcao: Direcao = "maior_melhor",
    tema: Tema = "claro",
    ambar: float | None = None,
    vermelho: float | None = None,
    uso: Literal["marca", "texto"] = "texto",
) -> str:
    """Atalho: :func:`nivel_delta` seguido de :func:`cor_nivel`."""
    return cor_nivel(
        nivel_delta(delta, direcao=direcao, ambar=ambar, vermelho=vermelho),
        tema=tema,
        uso=uso,
    )


def posicao_divergente(delta: float | None, *, direcao: Direcao, limite: float) -> float:
    """Normaliza um desvio para ``[-1, +1]`` em **favorabilidade**, nao em sinal.

    ``-1`` = totalmente desfavoravel (polo vermelho), ``+1`` = favoravel (azul).
    E o que a ponte por segmento e o heatmap de desvio devem passar para a
    escala divergente -- assim +7,20 p.p. de inadimplencia sai vermelho e
    +2,92% de faturamento sai azul, mesmo os dois sendo positivos.
    """
    if delta is None or delta != delta or not limite:
        return 0.0
    bruto = max(-1.0, min(1.0, delta / abs(limite)))
    return bruto if direcao != "menor_melhor" else -bruto


# --------------------------------------------------------------------------
# 6. Tipografia e espacamento
# --------------------------------------------------------------------------

#: As tres familias do Bancada, cada uma com um papel. Carregadas do Google
#: Fonts pelo ``@import`` de ``componentes.estilos()`` -- o ``config.toml`` do
#: Streamlit nao aceita URL de fonte.
#:
#: Toda stack declara fallback de verdade. O proprio sistema registra por que
#: isso importa: sem Plex Mono o fallback e Courier, um salto de genero
#: tipografico; sem Plex Sans e Segoe UI, **que tambem tem tabular**, entao o
#: alinhamento de coluna sobrevive.
FONTE: Final[str] = '"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

#: Rotulo em versalete, cabecalho de coluna, proveniencia. **Nunca numero**:
#: nesta superficie quem alinha coluna e ``tabular-nums``, nao a monoespacada.
FONTE_MONO: Final[str] = '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'

#: So o numero heroi do cartao de KPI. A 30px a mono leria como terminal.
FONTE_NUMERO: Final[str] = '"Archivo", "Arial Narrow", system-ui, sans-serif'

#: Escala tipografica em px. Quatro degraus de leitura, nao doze.
#:
#: Deliberadamente **nao** e a escala do Bancada, que e fluida (``clamp``) com
#: corpo de 16 a 17,8px: aquela e a escala de um site com prosa, e esta e a de
#: um painel operacional denso, onde o dono pediu menos rolagem. Do sistema vem
#: as familias, os pesos e o tabular; o tamanho continua nosso.
TIPOGRAFIA: Final[dict[str, int]] = {
    "numero_kpi": 28,     # valor do tile de KPI
    "titulo_secao": 16,
    "corpo": 14,
    "rotulo": 13,         # rotulo de eixo, legenda, delta
    "nota": 12,           # proveniencia, badge, aviso de armadilha
}

#: Espacamento em px -- escala de 4, como a do Bancada. Use so estes valores.
ESPACO: Final[dict[str, int]] = {
    "xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32,
}

#: Raio e traco. Os dois raios sao os do Bancada: 3px em bloco, 2px em controle.
#: Zero sombra em todo o app -- elevacao se comunica por superficie, nao borrao.
RAIO_CARD: Final[int] = 3
RAIO_MARCA: Final[int] = 2      # ponta arredondada de barra, ancorada na base
ESPESSURA_LINHA: Final[int] = 2
TAMANHO_MARCADOR: Final[int] = 8
FOLGA_ENTRE_MARCAS: Final[int] = 2  # respiro da superficie entre fatias e barras


def layout_grafico(tema: Tema = "claro") -> dict:
    """Dicionario de layout base do Plotly, coerente com os tokens.

    Nao importa Plotly -- devolve so o ``dict``, que o front-end passa em
    ``fig.update_layout(**layout_grafico(tema))``.
    """
    t = tokens(tema)
    return {
        # Numeros do Plotly em pt-BR: 1o char = decimal, 2o = milhar.
        # Sem isto os hovertemplates saem no padrao americano (1,234.56),
        # contradizendo frotas.ui.format no resto do app.
        "separators": ",.",
        "paper_bgcolor": t.superficie,
        "plot_bgcolor": t.superficie,
        # Sequencia padrao para qualquer traco que nao peca cor: o Plotly cairia
        # no azul dele, que nao pertence a nenhuma paleta deste app.
        "colorway": list(PALETA_DADOS),
        "font": {"family": FONTE, "size": TIPOGRAFIA["rotulo"], "color": t.tinta_secundaria},
        # "text" tem que vir explicito: um title so com "font" faz o Plotly.js
        # desenhar a string "undefined" no topo do grafico. Os titulos deste app
        # sao cabecalhos de secao em HTML, entao o padrao e vazio -- quem quiser
        # titulo dentro da figura passa title_text e sobrescreve.
        "title": {"text": "", "font": {"size": TIPOGRAFIA["titulo_secao"], "color": t.tinta}},
        # Grade vertical desligada, horizontal ligada: e a regra do Bancada (a
        # mesma do tema de Power BI dele) e a pratica corrente em serie temporal
        # -- a linha vertical nao ajuda a comparar altura e vira ruido.
        "xaxis": {
            "showgrid": False, "linecolor": t.eixo, "zerolinecolor": t.eixo,
            "tickfont": {"color": t.tinta_fraca, "size": TIPOGRAFIA["nota"]},
        },
        "yaxis": {
            "gridcolor": t.grade, "linecolor": t.eixo, "zerolinecolor": t.eixo,
            "tickfont": {"color": t.tinta_fraca, "size": TIPOGRAFIA["nota"]},
        },
        "hoverlabel": {
            "bgcolor": t.superficie_alta, "bordercolor": t.eixo,
            "font": {"family": FONTE, "size": TIPOGRAFIA["rotulo"], "color": t.tinta},
        },
        "legend": {
            "font": {"color": t.tinta_secundaria, "size": TIPOGRAFIA["nota"]},
            "bgcolor": "rgba(0,0,0,0)",
        },
        "margin": {"l": 48, "r": 16, "t": 32, "b": 40},
    }


__all__ = [
    "Tema", "Nivel", "Direcao", "Tokens",
    "TEMA_CLARO", "tokens",
    "PALETA_DADOS", "COR_OUTROS", "TRANSPARENTE",
    "paleta_categorica", "exige_rotulo_direto",
    "INDICADORES", "cor_indicador", "RATING_NIVEL", "cor_rating",
    "RAMPA_NEUTRA", "RAMPA_RISCO", "rampa",
    "ESCALA_DIVERGENTE", "escala_divergente", "posicao_divergente",
    "IDX_DIVERGENTE_FAVORAVEL", "IDX_DIVERGENTE_DESFAVORAVEL",
    "DIRECAO_KPI", "ICONE_NIVEL", "ROTULO_NIVEL",
    "nivel_por_limiar", "nivel_delta", "cor_nivel", "cor_delta",
    "FONTE", "FONTE_MONO", "FONTE_NUMERO",
    "TIPOGRAFIA", "ESPACO", "RAIO_CARD", "RAIO_MARCA",
    "ESPESSURA_LINHA", "TAMANHO_MARCADOR", "FOLGA_ENTRE_MARCAS", "layout_grafico",
]
