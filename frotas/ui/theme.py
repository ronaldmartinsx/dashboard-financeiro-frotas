"""Tokens de cor, paletas nomeadas e regras de cor por status.

Este modulo e a fonte de verdade visual do app. Nada aqui importa Streamlit: e
so dado e funcao pura, para poder ser testado num script e reaproveitado por
Plotly, Altair, HTML de componente e pelo ``.streamlit/config.toml``.

Como as paletas foram escolhidas
--------------------------------
Seguindo a skill ``dataviz``: forma primeiro, cor por ultimo, e validacao por
script -- nunca por olho. A paleta categorica dos 8 segmentos foi obtida
enumerando ordens candidatas e mantendo apenas as que passam **todos** os
portoes nos dois temas, contra as superficies reais do app
(``#FBFBF9`` claro, ``#16181C`` escuro):

* banda de luminosidade OKLCH e piso de croma: PASS nos dois temas;
* separacao para daltonismo (protan/deutan, Machado 2009): pior par adjacente
  **DeltaE 9,2 (claro)** e **9,4 (escuro)** -- alvo >= 8;
* piso de visao normal: **19,6 (claro)** e **19,3 (escuro)** -- piso >= 15;
* contraste vs. superficie: escuro passa inteiro; no claro tres matizes ficam
  abaixo de 3:1 (aqua, magenta, amarelo) e por isso **exigem rotulo direto ou
  tabela** (regra de alivio da skill, ver ``docs/03_ux.md`` secao 8).

O vermelho **saiu** da paleta categorica de proposito. Neste app vermelho e cor
de risco real (limiar vermelho da secao 8 de ``docs/01_kpis.md``); um segmento
pintado de vermelho competiria com o alerta. O slot vago foi para um ciano
proprio (``#0e8ea6`` / ``#2ba3bb``), validado junto com o resto.

Direcao da metrica
------------------
Metade dos KPIs melhora subindo (faturamento, margem, caixa) e metade melhora
descendo (inadimplencia, custo, carteira vencida). Por isso **nenhuma funcao
daqui pinta um numero pelo sinal**: pinta por *favorabilidade*, que depende de
:data:`DIRECAO_KPI`. E o que impede o erro classico de mostrar em verde uma
inadimplencia que subiu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Mapping

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


#: Tema claro. Superficie de card #FBFBF9 -- e contra ela que tudo foi validado.
TEMA_CLARO: Final[Tokens] = Tokens(
    nome="claro",
    plano="#F2F2EE",
    superficie="#FBFBF9",
    superficie_alta="#FFFFFF",
    superficie_fraca="#F6F5F1",
    tinta="#101112",
    tinta_secundaria="#52514E",
    tinta_fraca="#6E6D67",
    grade="#E4E3DC",
    eixo="#BFBEB7",
    borda="rgba(16, 17, 18, 0.10)",
    marca_bom="#0CA30C",
    marca_atencao="#FAB219",
    marca_serio="#EC835A",
    marca_critico="#D03B3B",
    marca_neutro="#9A9A93",
    marca_meta="#52514E",
    texto_bom="#0F7A12",
    texto_atencao="#8A5A00",
    texto_serio="#9A4A22",
    texto_critico="#B02525",
    texto_neutro="#6E6D67",
)

#: Tema escuro. Superficie de card #16181C -- passos proprios, nao um "inverso".
TEMA_ESCURO: Final[Tokens] = Tokens(
    nome="escuro",
    plano="#0E1013",
    superficie="#16181C",
    superficie_alta="#1E2126",
    superficie_fraca="#1A1D21",
    tinta="#FFFFFF",
    tinta_secundaria="#C4C7C2",
    tinta_fraca="#8E918C",
    grade="#2A2E33",
    eixo="#3E434A",
    borda="rgba(255, 255, 255, 0.12)",
    marca_bom="#0CA30C",
    marca_atencao="#FAB219",
    marca_serio="#EC835A",
    marca_critico="#D03B3B",
    marca_neutro="#77797D",
    marca_meta="#C4C7C2",
    texto_bom="#3FCB43",
    texto_atencao="#F2C14E",
    texto_serio="#F0A184",
    texto_critico="#FF8A8A",
    texto_neutro="#8E918C",
)

_TEMAS: Final[Mapping[Tema, Tokens]] = {"claro": TEMA_CLARO, "escuro": TEMA_ESCURO}


def tokens(tema: Tema = "claro") -> Tokens:
    """Tokens do tema pedido. ``tema`` invalido cai no claro, nunca explode."""
    return _TEMAS.get(tema, TEMA_CLARO)


# --------------------------------------------------------------------------
# 2. Paleta categorica -- identidade dos 8 segmentos
# --------------------------------------------------------------------------

#: Ordem fixa dos slots categoricos (claro, escuro). A ordem **e** o mecanismo
#: de seguranca para daltonismo: nao reordene sem rodar o validador da skill.
SLOTS_CATEGORICOS: Final[tuple[tuple[str, str, str], ...]] = (
    ("azul",    "#2A78D6", "#3987E5"),
    ("laranja", "#EB6834", "#D95926"),
    ("aqua",    "#1BAF7A", "#199E70"),
    ("violeta", "#4A3AA7", "#9085E9"),
    ("verde",   "#008300", "#008300"),
    ("magenta", "#E87BA4", "#D55181"),
    ("amarelo", "#EDA100", "#C98500"),
    ("ciano",   "#0E8EA6", "#2BA3BB"),
)

#: Segmento -> slot. Ordem alfabetica do dominio de ``clientes.segmento``: e
#: deterministica, documentada e **nunca repinta** quando um filtro reduz o
#: numero de series (regra "cor segue a entidade, nunca o rank").
#:
#: Coincidencia util e proposital: Construcao Civil -- o segmento que conta a
#: historia -- cai no laranja, saliente sem roubar o vermelho do alerta.
SEGMENTOS: Final[tuple[str, ...]] = (
    "Agronegocio",
    "Construcao Civil",
    "Energia e Saneamento",
    "Industria",
    "Logistica e Transporte",
    "Mineracao",
    "Servicos Publicos",
    "Varejo e Distribuicao",
)

#: Matizes cujo contraste no tema claro fica abaixo de 3:1. Onde eles aparecem,
#: a UI **tem** que oferecer rotulo direto ou a visao de tabela (regra de alivio).
_BAIXO_CONTRASTE_CLARO: Final[frozenset[str]] = frozenset({"#1BAF7A", "#E87BA4", "#EDA100"})

#: Cor de qualquer categoria fora do dominio conhecido ("Outros", nulo, resto do
#: Pareto). Nunca gerar um 9o matiz: dobre no cinza.
COR_OUTROS: Final[tuple[str, str]] = ("#9A9A93", "#77797D")

#: Preenchimento nulo -- a marca so tem contorno (barra fantasma do ano anterior,
#: por exemplo). Existe como token para que nenhuma view escreva cor na mao.
TRANSPARENTE: Final[str] = "rgba(0,0,0,0)"


#: Indicador orcado -> slot categorico. Cor **por indicador**, nao por segmento:
#: o indicador atravessa as quatro paginas (aparece em card, serie e matriz),
#: enquanto o segmento so pinta dois visuais. Quem le associa "laranja = custo"
#: em qualquer tela.
#:
#: Nenhum indicador recebe vermelho ou verde: sao as cores de status (critico e
#: dentro da meta). Uma serie de inadimplencia pintada de vermelho pareceria em
#: alerta permanente, inclusive quando o indicador esta bom.
#:
#: Segmento e indicador compartilham os mesmos oito slots, mas **nunca no mesmo
#: visual**: um grafico mostra series de indicadores ou de segmentos, jamais os
#: dois. A ambiguidade seria entre telas, e o rotulo direto resolve.
INDICADORES: Final[tuple[tuple[str, int], ...]] = (
    ("Faturamento", 0),          # azul -- a serie que abre a leitura
    ("Receita Liquida", 7),      # ciano -- parente do azul: faturamento menos impostos
    ("Recebimento (Caixa)", 2),  # aqua -- o dinheiro que entrou
    ("Custo Operacional", 1),    # laranja -- a saida
    ("Inadimplencia > 30d", 3),  # violeta -- risco sem usar o vermelho de alerta
)


def cor_indicador(indicador: str, tema: Tema = "claro") -> str:
    """Cor fixa de um indicador orcado, estavel em todas as paginas."""
    paleta = paleta_categorica(tema)
    for nome, slot in INDICADORES:
        if nome == indicador:
            return paleta[slot]
    return paleta[0]


def paleta_categorica(tema: Tema = "claro") -> list[str]:
    """Os 8 slots categoricos, na ordem validada."""
    indice = 1 if tema == "claro" else 2
    return [slot[indice] for slot in SLOTS_CATEGORICOS]


def paleta_segmentos(tema: Tema = "claro") -> dict[str, str]:
    """Mapa ``segmento -> hex``, fixo e independente do recorte ativo.

    Passe este dicionario inteiro para o grafico (``color_discrete_map`` no
    Plotly, ``scale=alt.Scale(domain=..., range=...)`` no Altair). Nunca deixe a
    biblioteca ciclar cores sozinha: um filtro que remove um segmento nao pode
    repintar os que sobraram.
    """
    cores = paleta_categorica(tema)
    return dict(zip(SEGMENTOS, cores))


def cor_segmento(segmento: str | None, tema: Tema = "claro") -> str:
    """Cor fixa de um segmento. Desconhecido/nulo -> cinza de "Outros"."""
    if not segmento:
        return COR_OUTROS[0 if tema == "claro" else 1]
    return paleta_segmentos(tema).get(
        segmento, COR_OUTROS[0 if tema == "claro" else 1]
    )


def exige_rotulo_direto(cor: str, tema: Tema = "claro") -> bool:
    """A cor fica abaixo de 3:1 na superficie e precisa de rotulo/tabela?"""
    return tema == "claro" and cor.upper() in _BAIXO_CONTRASTE_CLARO


# --------------------------------------------------------------------------
# 3. Rampas sequenciais -- magnitude
# --------------------------------------------------------------------------

#: Rampa neutra de magnitude (azul, matiz do slot 1). Use para grandeza **sem
#: polaridade**: faturamento, custo, carteira. Passos 100 (perto de zero) a 700.
RAMPA_NEUTRA: Final[dict[int, str]] = {
    100: "#CDE2FB", 150: "#B7D3F6", 200: "#9EC5F4", 250: "#86B6EF",
    300: "#6DA7EC", 350: "#5598E7", 400: "#3987E5", 450: "#2A78D6",
    500: "#256ABF", 550: "#1C5CAB", 600: "#184F95", 650: "#104281",
    700: "#0D366B",
}

#: Rampa de risco (vermelho, mesmo matiz do status critico, hue OKLCH 27).
#: Use **so** para grandeza que e risco: inadimplencia, vencido, atraso.
#: Fora disso, use :data:`RAMPA_NEUTRA` -- vermelho nao e decoracao.
RAMPA_RISCO: Final[dict[int, str]] = {
    100: "#FFE0DB", 150: "#FFCDC5", 200: "#FFB9AF", 250: "#FFA499",
    300: "#FB8D82", 350: "#F1786D", 400: "#E56359", 450: "#D74F47",
    500: "#C33933", 550: "#AF2C28", 600: "#982421", 650: "#811E1B",
    700: "#6B1715",
}

#: Passos permitidos numa rampa **ordinal** (celulas discretas, faixas, tiers):
#: o passo mais proximo da superficie ainda precisa de 2:1.
#: Validado: azul claro 250 (2,04:1) / azul escuro 500 (3,29:1);
#: risco claro 300 (2,19:1) / risco escuro 550 (2,72:1).
_LIMITES_ORDINAIS: Final[dict[tuple[str, Tema], tuple[int, int]]] = {
    ("neutra", "claro"): (250, 700),
    ("neutra", "escuro"): (100, 500),
    ("risco", "claro"): (300, 700),
    ("risco", "escuro"): (150, 550),
}

_RAMPAS: Final[dict[str, dict[int, str]]] = {
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
        nome: ``"neutra"`` (azul, grandeza sem polaridade) ou ``"risco"``
            (vermelho, so para risco real).
        tema: no tema escuro a ancora inverte -- "mais" fica **mais claro**,
            porque e o claro que avanca sobre o fundo escuro.
        n: quantos passos (2 a 9).
        ordinal: ``True`` para marcas discretas (celulas de heatmap, faixas de
            aging): respeita o piso de 2:1 do passo mais proximo da superficie.
            ``False`` libera a rampa inteira, para preenchimento continuo.

    Returns:
        Lista de hex na ordem "menor valor -> maior valor".
    """
    if nome not in _RAMPAS:
        raise ValueError(f"rampa desconhecida: {nome!r}. Use 'neutra' ou 'risco'.")
    n = max(2, min(9, int(n)))
    passos = sorted(_RAMPAS[nome])
    if ordinal:
        menor, maior = _LIMITES_ORDINAIS[(nome, tema)]
        passos = [p for p in passos if menor <= p <= maior]
    escolhidos = [
        passos[round(i * (len(passos) - 1) / (n - 1))] for i in range(n)
    ]
    cores = [_RAMPAS[nome][p] for p in escolhidos]
    # No tema escuro a intensidade cresce para o claro: inverte a ordem.
    return cores if tema == "claro" else list(reversed(cores))


# --------------------------------------------------------------------------
# 4. Escala divergente -- desvio favoravel x desfavoravel
# --------------------------------------------------------------------------
#
# ATENCAO: a escala divergente codifica **favorabilidade**, nao o sinal bruto.
# +7,20 p.p. de inadimplencia e o pior numero do dataset e tem que sair no polo
# desfavoravel, ainda que o numero seja positivo. Quem decide isso e
# DIRECAO_KPI, via posicao_divergente().

#: Polo desfavoravel (vermelho) -> neutro -> polo favoravel (azul).
#: Cinza no meio de proposito: no meio a leitura tem que ser "nada acontecendo".
ESCALA_DIVERGENTE: Final[dict[Tema, list[str]]] = {
    "claro": ["#AF2C28", "#D74F47", "#F1786D", "#EDECE8", "#86B6EF", "#3987E5", "#1C5CAB"],
    "escuro": ["#FFA499", "#F1786D", "#D74F47", "#2E3238", "#256ABF", "#3987E5", "#86B6EF"],
}


def escala_divergente(tema: Tema = "claro") -> list[str]:
    """Sete passos: 3 desfavoraveis, cinza neutro, 3 favoraveis."""
    return list(ESCALA_DIVERGENTE[tema])


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
    "eficiencia_cobranca": "maior_melhor",
    "recuperacao_vencidos": "maior_melhor",
    "mrr_contratado": "maior_melhor",
    "custo_operacional": "menor_melhor",
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

#: Uma familia so, a do sistema. Sem fonte display, sem serifada.
FONTE: Final[str] = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

#: Escala tipografica em px. Quatro degraus de leitura, nao doze.
TIPOGRAFIA: Final[dict[str, int]] = {
    "numero_heroi": 40,   # valor unico da pagina 1
    "numero_kpi": 28,     # valor do tile de KPI
    "titulo_pagina": 22,
    "titulo_secao": 16,
    "corpo": 14,
    "rotulo": 13,         # rotulo de eixo, legenda, delta
    "nota": 12,           # proveniencia, badge, aviso de armadilha
}

#: Espacamento em px -- escala de 4. Use so estes valores.
ESPACO: Final[dict[str, int]] = {
    "xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32,
}

#: Raio de canto e espessura de traco.
RAIO_CARD: Final[int] = 8
RAIO_MARCA: Final[int] = 4      # ponta arredondada de barra, ancorada na base
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
        "font": {"family": FONTE, "size": TIPOGRAFIA["rotulo"], "color": t.tinta_secundaria},
        # "text" tem que vir explicito: um title so com "font" faz o Plotly.js
        # desenhar a string "undefined" no topo do grafico. Os titulos deste app
        # sao cabecalhos de secao em HTML, entao o padrao e vazio -- quem quiser
        # titulo dentro da figura passa title_text e sobrescreve.
        "title": {"text": "", "font": {"size": TIPOGRAFIA["titulo_secao"], "color": t.tinta}},
        "xaxis": {
            "gridcolor": t.grade, "linecolor": t.eixo, "zerolinecolor": t.eixo,
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
    "TEMA_CLARO", "TEMA_ESCURO", "tokens",
    "SLOTS_CATEGORICOS", "SEGMENTOS", "COR_OUTROS",
    "paleta_categorica", "paleta_segmentos", "cor_segmento", "exige_rotulo_direto",
    "RAMPA_NEUTRA", "RAMPA_RISCO", "rampa",
    "ESCALA_DIVERGENTE", "escala_divergente", "posicao_divergente",
    "DIRECAO_KPI", "ICONE_NIVEL", "ROTULO_NIVEL",
    "nivel_por_limiar", "nivel_delta", "cor_nivel", "cor_delta",
    "FONTE", "TIPOGRAFIA", "ESPACO", "RAIO_CARD", "RAIO_MARCA",
    "ESPESSURA_LINHA", "TAMANHO_MARCADOR", "FOLGA_ENTRE_MARCAS", "layout_grafico",
]
