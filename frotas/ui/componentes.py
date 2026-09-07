"""Componentes reutilizaveis do app -- a secao 5 de ``docs/03_ux.md`` executavel.

Regras que este modulo existe para garantir (e que as views nao precisam repetir):

* **nenhuma cor nasce aqui**: todo hex vem de :mod:`frotas.ui.theme`;
* **nenhum numero e formatado na mao**: tudo passa por :mod:`frotas.ui.format`;
* **nenhum limiar de alerta e conhecido**: nivel e cor chegam prontos de
  ``frotas.metrics.alertas.avaliar()``; aqui so se traduz ``nivel`` em token;
* **cor nunca viaja sozinha**: todo estado sai com glifo (``ICONE_NIVEL``) e
  rotulo textual (``ROTULO_NIVEL``), como pede a secao 8 do UX.

Os componentes desenham HTML proprio em vez de usar ``st.metric`` porque a
anatomia pedida (rotulo, valor 28px em tinta primaria, delta colorido, rodape de
periodo da meta, badges, altura fixa) nao cabe no widget nativo -- e porque a
regra mais importante do tile e que **o numero grande nunca e colorido**.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Mapping, Sequence

import pandas as pd
import streamlit as st

from frotas.ui import format as fmt
from frotas.ui import theme
from frotas.ui.theme import Direcao, Nivel, Tema

Estado = Literal["normal", "carregando", "erro", "sem_dado", "sem_meta"]
Unidade = Literal["brl", "pct", "num", "dias"]
UnidadeDelta = Literal["pp", "pct", "brl", "num"]
Escala = Literal["neutra", "risco", "divergente"]

#: Vocabulario fechado de badges (UX 5.8). Nao inventar badge novo.
BADGES_CONHECIDOS: tuple[str, ...] = (
    "escopo: contratos",
    "Janela de 12 meses",
    "janela de 12m incompleta",
)

#: Traducao ``alertas.avaliar().nivel`` -> nivel visual de ``theme``.
#: ``indisponivel`` vira **neutro** (cinza), nunca ``bom``: ausencia de regra
#: aplicavel nao e boa noticia.
NIVEL_ALERTA: Mapping[str, Nivel] = {
    "vermelho": "critico",
    "ambar": "atencao",
    "ok": "bom",
    "indisponivel": "neutro",
}

_CHAVE_ESTILOS = "_fv_estilos_aplicados"


# --------------------------------------------------------------------------
# Tema e folha de estilo
# --------------------------------------------------------------------------


def tema_atual() -> Tema:
    """O tema do app. Sempre claro.

    Nao le mais a preferencia do navegador: este painel e claro por tese, nao por
    gosto. Na camada de dados do Bancada o dashboard **e** o artefato claro que a
    bancada escura enquadra, e um print dele em tema escuro deixaria de pertencer
    a moldura do portfolio. O ``config.toml`` fixa ``base = "light"`` pelo mesmo
    motivo.
    """
    return "claro"


def _e(texto: Any) -> str:
    """Escapa texto para interpolar em HTML **e** neutraliza o cifrao.

    O Markdown do Streamlit trata ``$...$`` como LaTeX. Um texto com dois "R$"
    (comum aqui: "R$ 12 mil de R$ 30 mil") vira formula: o miolo sai sem espacos
    e os asteriscos de negrito aparecem como simbolos. Trocar por ``&#36;``
    mostra o mesmo cifrao sem abrir modo matematico.
    """
    return html.escape("" if texto is None else str(texto), quote=True).replace("$", "&#36;")


def reiniciar_estilos() -> None:
    """Marca que a folha de estilo ainda nao foi injetada NESTE rerun.

    Chamada no topo do ``streamlit_app.py``. Sem isto o guard de ``estilos()``
    -- que vive em ``session_state``, e portanto sobrevive ao rerun -- impediria
    a reinjecao do ``<style>``, que o Streamlit recria a cada rerun. O sintoma
    era a pagina voltar sem estilo ao trocar de pagina ou mexer num filtro,
    so voltando ao normal com F5 (sessao nova).
    """
    st.session_state.pop(_CHAVE_ESTILOS, None)


def estilos(tema: Tema = "claro") -> None:
    """Injeta a folha de estilo do app. Idempotente dentro de um mesmo rerun.

    Todos os valores vem de ``theme``: superficies, tinta, chrome, escala
    tipografica (``TIPOGRAFIA``), espacamento (``ESPACO``) e raio (``RAIO_CARD``).

    O guard evita ``<style>`` duplicado quando o entrypoint e a pagina chamam os
    dois; quem o zera a cada rerun e :func:`reiniciar_estilos`.
    """
    if st.session_state.get(_CHAVE_ESTILOS) == tema:
        return
    st.session_state[_CHAVE_ESTILOS] = tema
    t = theme.tokens(tema)
    tp, esp = theme.TIPOGRAFIA, theme.ESPACO
    st.markdown(
        f"""
<style>
/* As tres familias do Bancada. O @import tem que vir antes de qualquer regra,
   senao o navegador o descarta. O config.toml do Streamlit nao aceita URL de
   fonte, entao este e o unico ponto de carregamento de fonte do app. */
@import url("https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap");
:root {{
  --fv-plano: {t.plano};
  --fv-superficie: {t.superficie};
  --fv-superficie-alta: {t.superficie_alta};
  --fv-superficie-fraca: {t.superficie_fraca};
  --fv-tinta: {t.tinta};
  --fv-tinta-2: {t.tinta_secundaria};
  --fv-tinta-3: {t.tinta_fraca};
  --fv-grade: {t.grade};
  --fv-eixo: {t.eixo};
  --fv-borda: {t.borda};
  /* A marca da pagina. Era referenciada em .fv-leitura sem nunca ter sido
     definida: a barra da leitura executiva saia na cor do texto. */
  --fv-marca: {theme.cor_indicador("Faturamento", tema)};
  --fv-raio: {theme.RAIO_CARD}px;
  --fv-raio-controle: {theme.RAIO_MARCA}px;
  --fv-fonte: {theme.FONTE};
  --fv-fonte-mono: {theme.FONTE_MONO};
  --fv-fonte-numero: {theme.FONTE_NUMERO};
}}
.fv-tile {{
  background: var(--fv-superficie);
  border: 1px solid var(--fv-borda);
  border-radius: var(--fv-raio);
  padding: {esp['lg']}px;
  /* Altura minima do card com rotulo + numero. Delta, nota e badges
     empurram conforme existem: pagina sem meta nao carrega o vao de
     um card cheio. */
  min-height: 104px;
  display: flex; flex-direction: column; gap: {esp['xs']}px;
  font-family: var(--fv-fonte);
}}
.fv-tile--fraco {{ background: var(--fv-superficie-fraca); }}
.fv-tile__topo {{
  display: flex; align-items: baseline; justify-content: space-between;
  gap: {esp['sm']}px;
}}
/* Rotulo em versalete mono: no Bancada, versalete e exclusividade da mono, e a
   mono e exclusividade do rotulo. text-transform nao altera o DOM, entao o
   verificador de rotulos continua lendo o texto original. */
.fv-tile__rotulo {{
  font-family: var(--fv-fonte-mono);
  font-size: {tp['nota']}px; color: var(--fv-tinta-2); font-weight: 500;
  letter-spacing: .14em; text-transform: uppercase; line-height: 1.3;
}}
/* Numero heroi em Archivo tabular. Tabular e o que alinha o numero entre os
   cinco cards da faixa; nao e enfeite. */
.fv-tile__valor {{
  font-family: var(--fv-fonte-numero);
  font-variant-numeric: tabular-nums; font-feature-settings: "tnum";
  font-size: {tp['numero_kpi']}px; font-weight: 500; color: var(--fv-tinta);
  letter-spacing: -.02em; line-height: 1.15; margin-top: {esp['xs']}px;
}}
.fv-tile__delta {{
  font-variant-numeric: tabular-nums;
  font-size: {tp['rotulo']}px; line-height: 1.3;
}}
.fv-tile__nota {{
  font-size: {tp['nota']}px; color: var(--fv-tinta-3); line-height: 1.35;
  margin-top: auto;
}}
.fv-cab__kicker {{
  font-family: var(--fv-fonte-mono);
  font-size: {tp['nota']}px; color: var(--fv-tinta-2); font-weight: 500;
  letter-spacing: .14em; text-transform: uppercase; vertical-align: middle;
}}
.fv-cab__chips {{
  display: flex; flex-wrap: wrap; gap: {esp['xs']}px;
  margin: -{esp['xs']}px 0 {esp['lg']}px;
}}
.fv-badges {{ display: flex; flex-wrap: wrap; gap: {esp['xs']}px; margin-top: {esp['xs']}px; }}
/* Chip de contexto e badge: mono, como todo rotulo. Acromatico de proposito --
   no Bancada, cor pertence ao dado, nunca ao cromo da interface. */
.fv-badge {{
  display: inline-flex; align-items: center; gap: {esp['xs']}px;
  font-family: var(--fv-fonte-mono);
  font-size: {tp['nota']}px; line-height: 1.4;
  background: var(--fv-superficie-fraca); color: var(--fv-tinta-2);
  border: 1px solid var(--fv-borda); border-radius: var(--fv-raio-controle);
  padding: 2px {esp['sm']}px; white-space: nowrap;
}}
.fv-esqueleto {{
  background: var(--fv-superficie-fraca); border-radius: var(--fv-raio-controle);
}}
.fv-banner {{
  display: flex; align-items: flex-start; gap: {esp['md']}px;
  background: var(--fv-superficie);
  border: 1px solid var(--fv-borda); border-radius: var(--fv-raio);
  border-left-width: 4px; border-left-style: solid;
  padding: {esp['md']}px {esp['lg']}px;
  /* Respiro acima: o banner agora vem logo abaixo da faixa de KPIs e, sem esta
     margem, encostava nos cards. */
  margin: {esp['lg']}px 0 {esp['sm']}px;
  font-family: var(--fv-fonte);
}}
/* Banners consecutivos nao repetem o respiro: so o primeiro se afasta dos cards. */
.fv-banner + .fv-banner {{ margin-top: 0; }}
.fv-banner__glifo {{ font-size: {tp['corpo']}px; line-height: 1.4; }}
.fv-banner__corpo {{ display: flex; flex-direction: column; gap: 2px; min-width: 0; }}
.fv-banner__titulo {{
  font-size: {tp['corpo']}px; color: var(--fv-tinta); font-weight: 600; line-height: 1.35;
}}
.fv-banner__detalhe {{ font-size: {tp['rotulo']}px; color: var(--fv-tinta-2); line-height: 1.4; }}
.fv-banner__entidades {{ font-size: {tp['nota']}px; color: var(--fv-tinta-3); line-height: 1.4; }}
.fv-banner__acao {{ margin-left: auto; font-size: {tp['rotulo']}px; white-space: nowrap; }}
.fv-banner__acao a {{ color: var(--fv-tinta-2); text-decoration: none; border-bottom: 1px solid var(--fv-eixo); }}
.fv-banner--linha {{
  border-left-width: 1px; padding: {esp['sm']}px {esp['lg']}px;
  font-size: {tp['rotulo']}px;
}}
.fv-secao {{ margin: {esp['xl']}px 0 {esp['sm']}px; font-family: var(--fv-fonte); }}
.fv-secao__linha {{ display: flex; align-items: baseline; gap: {esp['md']}px; }}
.fv-secao__pergunta {{
  font-size: {tp['titulo_secao']}px; font-weight: 600; color: var(--fv-tinta);
  line-height: 1.3; margin: 0;
}}
.fv-secao__apoio {{ font-size: {tp['rotulo']}px; color: var(--fv-tinta-2); line-height: 1.4; margin-top: 2px; }}
.fv-secao__acao {{ margin-left: auto; font-size: {tp['rotulo']}px; white-space: nowrap; }}
.fv-secao__acao a {{ color: var(--fv-tinta-2); text-decoration: none; border-bottom: 1px solid var(--fv-eixo); }}
.fv-nota {{
  display: flex; gap: {esp['sm']}px; align-items: flex-start;
  background: var(--fv-superficie-fraca); border-left: 2px solid var(--fv-eixo);
  border-radius: {theme.RAIO_MARCA}px; padding: {esp['sm']}px {esp['md']}px;
  font-size: {tp['nota']}px; color: var(--fv-tinta-2); line-height: 1.45;
  /* Mesmo respiro do banner: a nota tambem aparece logo abaixo da faixa de
     KPIs e, sem margem no topo, encostava nos cards. */
  margin: {esp['lg']}px 0 {esp['sm']}px; font-family: var(--fv-fonte);
}}
/* Notas ou banners em sequencia nao repetem o respiro. */
.fv-nota + .fv-nota, .fv-banner + .fv-nota, .fv-nota + .fv-banner {{ margin-top: 0; }}

/* Leitura executiva: texto gerado, com o selo de conferencia no rodape. Mesma
   familia visual da nota de armadilha, mas com respiro de bloco de leitura. */
.fv-leitura {{
  border-left: 3px solid var(--fv-marca);
  background: var(--fv-superficie-fraca);
  padding: {esp['md']}px {esp['lg']}px {esp['sm']}px;
  margin: {esp['sm']}px 0 {esp['md']}px;
  font-family: var(--fv-fonte); font-size: {tp['corpo']}px; color: var(--fv-tinta);
}}
.fv-leitura p {{ margin: 0 0 {esp['sm']}px; line-height: 1.62; }}
.fv-leitura p:last-of-type {{ margin-bottom: 0; }}
.fv-leitura__selo {{
  display: block; margin-top: {esp['md']}px; padding-top: {esp['sm']}px;
  border-top: 1px solid var(--fv-grade);
  font-size: {tp['nota']}px; color: var(--fv-tinta-3);
}}
.fv-vazio {{
  border: 1px dashed var(--fv-eixo); border-radius: var(--fv-raio);
  padding: {esp['xl']}px; text-align: center; font-family: var(--fv-fonte);
  background: var(--fv-superficie-fraca);
}}
.fv-vazio__titulo {{ font-size: {tp['corpo']}px; color: var(--fv-tinta); font-weight: 600; }}
.fv-vazio__corpo {{ font-size: {tp['rotulo']}px; color: var(--fv-tinta-2); margin-top: {esp['xs']}px; }}
.fv-frase {{
  font-size: {tp['corpo']}px; color: var(--fv-tinta-2); line-height: 1.6;
  font-family: var(--fv-fonte);
}}
.fv-frase b {{ color: var(--fv-tinta); font-weight: 600; }}
/* Rodape de assinatura. Separado do conteudo por **fio**, nunca por inversao de
   fundo -- regra do Footer do Bancada. Acromatico: a cor pertence ao dado. */
.fv-rodape {{
  border-top: 1px solid var(--fv-borda);
  margin-top: {esp['xxl']}px; padding-top: {esp['lg']}px; padding-bottom: {esp['lg']}px;
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: {esp['lg']}px; flex-wrap: wrap;
  font-family: var(--fv-fonte-mono);
  font-size: {tp['nota']}px; line-height: 1.5; color: var(--fv-tinta-3);
}}
.fv-rodape__linha {{
  display: flex; flex-wrap: wrap; align-items: center;
  gap: {esp['xs']}px {esp['lg']}px; min-width: 0;
}}
.fv-rodape strong {{ color: var(--fv-tinta-2); font-weight: 500; }}
/* Link sem cromatico: sobe para a tinta do titulo e sublinha no fio de controle,
   como o --link da camada de dados manda. */
.fv-rodape a {{
  color: var(--fv-tinta); text-decoration: none;
  border-bottom: 1px solid var(--fv-eixo);
}}
.fv-rodape a:hover {{ border-bottom-color: var(--fv-marca); }}
/* Glifo de plataforma: acompanha o nome, herda a tinta e nao entra em circulo
   preenchido -- as tres regras que o Bancada poe sobre marca de terceiro. */
.fv-rodape__plataforma {{
  display: inline-flex; align-items: center; gap: {esp['xs']}px;
}}
.fv-rodape__sinal {{ flex: none; color: var(--fv-tinta-2); margin-top: 2px; }}

/* Todo numero desta folha e tabular: e o que alinha coluna e faixa de KPI. */
.fv-tile__valor, .fv-tile__delta, .fv-tile__nota,
.fv-banner__detalhe, .fv-leitura__selo {{
  font-variant-numeric: tabular-nums; font-feature-settings: "tnum";
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
</style>
""",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# 5.8 badge
# --------------------------------------------------------------------------


def badge(texto: str, *, nivel: Nivel = "neutro") -> str:
    """Devolve o HTML de um badge (12px, superficie fraca, raio 4px).

    Nao renderiza sozinho de proposito: badges quase sempre entram dentro de
    outro componente (tile, cabecalho de tabela). Para exibir solto, use
    :func:`linha_badges`.

    O vocabulario e fechado (:data:`BADGES_CONHECIDOS` + ``Posição em {data}`` e
    ``{ano} e parcial ({n} meses)``); textos livres passam, mas a revisao de UX
    e quem decide se entram.
    """
    glifo = "" if nivel == "neutro" else f'<span aria-hidden="true">{theme.ICONE_NIVEL[nivel]}</span>'
    return f'<span class="fv-badge">{glifo}{_e(texto)}</span>'


def linha_badges(badges: Sequence[str], *, nivel: Nivel = "neutro") -> None:
    """Renderiza uma linha de badges."""
    if not badges:
        return
    html_badges = "".join(badge(b, nivel=nivel) for b in badges)
    st.markdown(f'<div class="fv-badges">{html_badges}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 5.7 nota_armadilha
# --------------------------------------------------------------------------


def nota_armadilha(texto: str, *, tom: Literal["info", "aviso"] = "info") -> None:
    """Nota informativa -- **nunca** um alerta, e por isso **nunca** colorida.

    Glifo + texto em 12px sobre superficie fraca, com borda esquerda em ``eixo``.
    E o componente que carrega os textos da secao 6.5 do UX (as armadilhas).
    ``tom='aviso'`` troca so o glifo; a cor continua neutra de proposito -- se o
    texto merecesse cor, ele seria um alerta e viria de ``alertas.avaliar()``.
    """
    glifo = "ⓘ" if tom == "info" else "⚠"
    st.markdown(
        f'<div class="fv-nota"><span aria-hidden="true">{glifo}</span>'
        f"<span>{_e(texto)}</span></div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# 5.3 cabecalho_secao
# --------------------------------------------------------------------------


def cabecalho_secao(
    pergunta: str,
    *,
    apoio: str | None = None,
    nota: str | None = None,
    acao: tuple[str, str] | None = None,
    ancora: str | None = None,
) -> None:
    """Cabecalho de secao. Regra editorial: ``pergunta`` termina em ``?``.

    Args:
        pergunta: a pergunta de negocio que a secao responde (regra D1).
        apoio: subtitulo curto, 13px em tinta secundaria.
        nota: texto de armadilha, renderizado por :func:`nota_armadilha`.
        acao: ``(rotulo, destino)`` -- link a direita (``/pagina`` ou ``#ancora``).
        ancora: id do bloco, para o banner de alerta poder apontar para ca.
    """
    id_html = f' id="{_e(ancora)}"' if ancora else ""
    link = (
        f'<div class="fv-secao__acao"><a href="{_e(acao[1])}">{_e(acao[0])} ›</a></div>'
        if acao
        else ""
    )
    apoio_html = f'<div class="fv-secao__apoio">{_e(apoio)}</div>' if apoio else ""
    st.markdown(
        f'<div class="fv-secao"{id_html}>'
        f'<div class="fv-secao__linha"><h3 class="fv-secao__pergunta">{_e(pergunta)}</h3>{link}</div>'
        f"{apoio_html}</div>",
        unsafe_allow_html=True,
    )
    if nota:
        nota_armadilha(nota)


# --------------------------------------------------------------------------
# 5.1 tile_kpi
# --------------------------------------------------------------------------


def _texto_valor(valor: Any, unidade: Unidade, casas: int | None = None) -> str:
    if fmt.eh_vazio(valor):
        return fmt.VAZIO
    if unidade == "brl":
        return fmt.moeda_compacta(valor)
    if unidade == "pct":
        return fmt.percentual(valor, 1 if casas is None else casas)
    if unidade == "dias":
        return fmt.dias(valor)
    return fmt.contagem(valor)


#: Nome do produto. Aparece no cabecalho de toda pagina e na aba do navegador.
NOME_APP = "Dashboard Financeiro"

#: Icone de cada secao, em Material Symbols. Fonte unica: o ``st.navigation`` do
#: entrypoint e o cabecalho da pagina leem daqui, entao o icone do menu e o do
#: topo da pagina nunca divergem.
ICONE_SECAO: Mapping[str, str] = {
    "Guia": ":material/menu_book:",
    "Metas": ":material/flag:",
    "Faturamento e Recebimento": ":material/receipt_long:",
    "Inadimplência": ":material/gavel:",
    "Custos": ":material/payments:",
}


def cabecalho_pagina(
    secao: str,
    pergunta: str,
    *,
    chips: Sequence[str] = (),
    tema: Tema = "claro",
) -> None:
    """Cabecalho de toda pagina: identidade, pergunta e o recorte apurado.

    Tres camadas, de cima para baixo:

    1. ``Dashboard Financeiro · <secao>`` -- onde o leitor esta;
    2. a **pergunta de negocio**, que e o titulo da pagina;
    3. os ``chips`` de contexto: periodo de competencia, data da posicao, versao do
       orcamento e os recortes ativos.

    Os chips ficam **no topo**, e nao num rodape de proveniencia, porque contexto
    de apuracao e o que se precisa saber *antes* de ler o numero. E porque o
    recorte dimensional so aparecia na barra lateral: com ela recolhida, os
    numeros mudavam sem nada na tela dizendo por que.
    """
    # A diretiva ``:material/x:`` fica **fora** da tag: dentro de HTML bruto o
    # Streamlit nao a reprocessa e ela sairia literal na tela.
    icone = ICONE_SECAO.get(secao, "")
    prefixo = f"{icone} " if icone else ""
    st.markdown(
        f'{prefixo}<span class="fv-cab__kicker">{_e(NOME_APP)} · {_e(secao)}</span>',
        unsafe_allow_html=True,
    )
    st.title(pergunta)
    linha_chips(chips)


def linha_chips(chips: Sequence[str]) -> None:
    """So a faixa de chips do cabecalho.

    Existe separada porque a pagina de inadimplencia divide o topo em colunas
    (titulo | seletor de data) e os chips precisam vir depois, ja com a data
    que o usuario escolheu.
    """
    if not chips:
        return
    st.markdown(
        f'<div class="fv-cab__chips">{"".join(badge(c) for c in chips)}</div>',
        unsafe_allow_html=True,
    )


def tile_kpi(
    rotulo: str,
    valor: float | None,
    unidade: Unidade,
    *,
    chave_direcao: str,
    meta: float | None = None,
    delta: float | None = None,
    unidade_delta: UnidadeDelta = "pp",
    ambar: float | None = None,
    vermelho: float | None = None,
    periodo_meta: str | None = None,
    badges: Sequence[str] = (),
    nota: str | None = None,
    ajuda: str | None = None,
    casas: int | None = None,
    estado: Estado = "normal",
    tema: Tema = "claro",
) -> None:
    """Tile de KPI com delta versus meta (UX 5.1).

    **O numero grande nunca e colorido**: ele e sempre ``tinta``. Cor vive so no
    delta (glifo + texto), resolvida por :func:`frotas.ui.format.delta` a partir
    da direcao do KPI (``theme.DIRECAO_KPI[chave_direcao]``) e dos limiares que o
    chamador recebeu de ``alertas.avaliar()``. Sem limiares, desvio desfavoravel
    sai neutro -- a UI nao inventa severidade.

    Args:
        rotulo: nome do KPI, 13px em tinta secundaria.
        valor: o numero apurado, ja na escala final (``10.02`` para 10,02%).
        unidade: ``brl`` · ``pct`` · ``num`` · ``dias``.
        chave_direcao: chave de :data:`frotas.ui.theme.DIRECAO_KPI`.
        meta: valor da meta, so para compor o rodape.
        delta: desvio ja calculado (``variacao_abs`` em p.p. ou ``variacao_pct``).
        unidade_delta: ``pp`` para metrica que ja e percentual, ``pct`` para BRL.
        ambar / vermelho: limiares vindos da camada de alertas, em modulo.
        periodo_meta: **obrigatorio quando ha meta** (regra D6 do UX): o texto da
            janela usada, ex. ``meta de jan/2026 a ago/2026 = R$ 23,92 mi``.
        badges: vocabulario fechado -- ver :data:`BADGES_CONHECIDOS`.
        nota: rodape curto (janela usada, definicao, motivo da ausencia).
        ajuda: tooltip do ``ⓘ`` com formula e armadilha.
        estado: ``normal`` · ``carregando`` · ``erro`` · ``sem_dado`` · ``sem_meta``.
    """
    direcao: Direcao = theme.DIRECAO_KPI.get(chave_direcao, "neutro")
    if estado == "normal" and fmt.eh_vazio(valor):
        estado = "sem_dado"
    if estado == "normal" and fmt.eh_vazio(delta) and fmt.eh_vazio(meta):
        estado = "sem_meta"

    # Sem icone de ajuda no tile: o Streamlit sanitiza o HTML no cliente e remove
    # o atributo "title" de <span>, entao o ⓘ aparecia prometendo um tooltip que
    # nunca abria. As definicoes de cada indicador vivem no Guia do relatorio.
    # O parametro `ajuda` continua aceito (documenta a metrica no codigo) e alimenta
    # o rotulo acessivel, mas nao desenha nada.
    ajuda_html = ""
    classe = "fv-tile fv-tile--fraco" if estado in ("sem_dado", "carregando") else "fv-tile"
    lista_badges = list(badges)
    acessivel = ""

    if estado == "carregando":
        # Esqueleto: nunca spinner por cima do valor antigo -- numero velho com
        # aparencia de novo e o pior erro possivel numa tela de CFO.
        corpo = (
            f'<div class="fv-esqueleto" style="height:{theme.TIPOGRAFIA["numero_kpi"]}px;'
            f'width:60%;margin-top:{theme.ESPACO["sm"]}px"></div>'
            f'<div class="fv-esqueleto" style="height:{theme.TIPOGRAFIA["rotulo"]}px;'
            f'width:40%;margin-top:{theme.ESPACO["sm"]}px"></div>'
        )
        rodape = ""
    elif estado == "erro":
        cor = theme.cor_nivel("critico", tema, uso="texto")
        corpo = f'<div class="fv-tile__valor">{fmt.VAZIO}</div>'
        rodape = (
            f'<div class="fv-tile__delta" style="color:{cor}">'
            f'{theme.ICONE_NIVEL["critico"]} nao foi possivel calcular</div>'
        )
        acessivel = "nao foi possivel calcular"
    else:
        texto_valor = _texto_valor(valor, unidade, casas)
        d = fmt.delta(
            delta,
            unidade=unidade_delta,
            direcao=direcao,
            ambar=ambar,
            vermelho=vermelho,
            tema=tema,
        )
        corpo = f'<div class="fv-tile__valor">{_e(texto_valor)}</div>'
        if estado == "sem_meta" or fmt.eh_vazio(delta):
            # Sem meta nao ha delta, e "– —" embaixo do numero nao dizia nada:
            # um glifo de "sem sinal" ao lado de um travessao de "sem valor".
            # A linha simplesmente nao aparece.
            rodape = ""
            # Sem badge "meta indisponivel neste recorte": o travessao ja diz que
            # nao ha comparacao, e o badge repetido em cada tile virava ruido.
            acessivel = f"{texto_valor}, sem meta no recorte"
        else:
            # O glifo e a cor ja classificam o desvio; escrever "(dentro da meta)"
            # ao lado era a mesma informacao em texto, competindo com o numero.
            # O rotulo continua no aria-label, para quem usa leitor de tela.
            sufixo = " vs meta" if periodo_meta else ""
            glifo_html = f'<span aria-hidden="true">{d.icone}</span> ' if d.icone else ""
            rodape = (
                f'<div class="fv-tile__delta" style="color:{d.cor}">'
                f'{glifo_html}{_e(d.texto)}{sufixo}</div>'
            )
            acessivel = f"{texto_valor}, {d.acessivel}"

    if estado == "sem_dado":
        corpo = f'<div class="fv-tile__valor">{fmt.VAZIO}</div>'
        cor_neutra = theme.cor_nivel("neutro", tema, uso="texto")
        rodape = (
            f'<div class="fv-tile__delta" style="color:{cor_neutra}">'
            f'{theme.ICONE_NIVEL["neutro"]} {fmt.VAZIO}</div>'
        )
        acessivel = "sem dado no recorte"

    partes_nota = [p for p in (periodo_meta, nota) if p]
    nota_html = (
        f'<div class="fv-tile__nota">{"<br/>".join(_e(p) for p in partes_nota)}</div>'
        if partes_nota
        else ""
    )
    badges_html = (
        f'<div class="fv-badges">{"".join(badge(b) for b in lista_badges)}</div>'
        if lista_badges
        else ""
    )
    # A definicao da metrica sai da tela mas continua no rotulo acessivel: quem usa
    # leitor de tela nao ve a secao do Guia enquanto navega pelos tiles.
    rotulo_acessivel = f"{_e(rotulo)}: {_e(acessivel)}" + (f". {_e(ajuda)}" if ajuda else "")
    st.markdown(
        f'<div class="{classe}" role="group" aria-label="{rotulo_acessivel}">'
        f'<div class="fv-tile__topo"><span class="fv-tile__rotulo">{_e(rotulo.upper())}</span>{ajuda_html}</div>'
        f"{corpo}{rodape}{nota_html}{badges_html}</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# 5.2 banner_alerta
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Alerta:
    """Um alerta ja traduzido para a linguagem da tela.

    Nasce de ``frotas.metrics.alertas.avaliar()`` via :func:`alertas_da_camada`.
    A view **nao** monta um destes na mao a partir de um limiar proprio.
    """

    id: str
    nivel: Nivel
    titulo: str
    detalhe: str = ""
    acao: str | None = None
    destino: str | None = None
    entidades: str = ""
    impacto: float = 0.0


_ORDEM_NIVEL: Mapping[Nivel, int] = {"critico": 0, "atencao": 1, "serio": 1, "bom": 2, "neutro": 3}


def _valor_alerta(valor: Any, unidade: str) -> str:
    """Formata o ``valor`` de um alerta conforme a ``unidade`` que a camada mandou."""
    if fmt.eh_vazio(valor):
        return ""
    unidade = (unidade or "").strip().lower()
    if unidade == "p.p.":
        return fmt.pontos_percentuais(valor)
    if unidade in ("%", "% da meta", "% do custo", "% do faturamento"):
        return fmt.percentual(valor, 1)
    if unidade == "x empresa":
        return fmt.vezes(valor)
    if unidade.startswith("r$"):
        return fmt.moeda_compacta(valor)
    return fmt.contagem(valor)


def alertas_da_camada(
    df: pd.DataFrame,
    *,
    paginas: Sequence[int] | None = None,
    destinos: Mapping[str, str] | None = None,
    incluir_ok: bool = False,
) -> list[Alerta]:
    """Converte o DataFrame de ``alertas.avaliar()`` em :class:`Alerta`.

    Nao aplica nenhum limiar: ``nivel`` ja vem decidido pela camada semantica e
    aqui so e traduzido em token visual (:data:`NIVEL_ALERTA`). ``indisponivel``
    vira cinza com o motivo, nunca verde.

    Args:
        df: saida de ``alertas.avaliar()``.
        paginas: filtra por ``pagina`` (``0`` = qualidade de dado, todas as telas).
        destinos: ``{id_alerta: href}`` para o link "detalhe ›".
        incluir_ok: mantem as regras em ``ok``/``indisponivel`` (padrao: so as
            que dispararam).
    """
    if df is None or df.empty:
        return []
    recorte = df if paginas is None else df[df["pagina"].isin(list(paginas))]
    if not incluir_ok:
        recorte = recorte[recorte["nivel"].isin(("vermelho", "ambar"))]
    destinos = destinos or {}
    alertas: list[Alerta] = []
    for _, linha in recorte.iterrows():
        nivel = NIVEL_ALERTA.get(str(linha["nivel"]), "neutro")
        # O titulo usa o valor de **exibicao** da camada semantica, que pode estar
        # em outra unidade que a da regra: o A8 dispara em percentual do limite e
        # mostra reais, porque percentual de limites diferentes nao tem magnitude.
        texto_valor = _valor_alerta(
            linha.get("valor_exibido", linha.get("valor")),
            str(linha.get("unidade_exibida") or linha.get("unidade", "")),
        )
        titulo = str(linha["titulo"])
        if texto_valor:
            titulo = f"{titulo}: {texto_valor}"
        destino = destinos.get(str(linha["id"]))
        alertas.append(
            Alerta(
                id=str(linha["id"]),
                nivel=nivel,
                titulo=titulo,
                detalhe=str(linha.get("detalhe") or ""),
                entidades=str(linha.get("entidades") or ""),
                acao="detalhe" if destino else None,
                destino=destino,
                impacto=float(linha.get("qtd_vermelho") or 0) * 1e6
                + float(linha.get("qtd_ambar") or 0),
            )
        )
    return alertas


def _linha_banner(alerta: Alerta, tema: Tema) -> str:
    cor_marca = theme.cor_nivel(alerta.nivel, tema, uso="marca")
    cor_texto = theme.cor_nivel(alerta.nivel, tema, uso="texto")
    glifo = theme.ICONE_NIVEL[alerta.nivel]
    rotulo = theme.ROTULO_NIVEL[alerta.nivel]
    acao = (
        f'<div class="fv-banner__acao"><a href="{_e(alerta.destino)}">{_e(alerta.acao)} ›</a></div>'
        if alerta.destino and alerta.acao
        else ""
    )
    entidades = (
        f'<div class="fv-banner__entidades">{_e(alerta.entidades)}</div>'
        if alerta.entidades
        else ""
    )
    return (
        f'<div class="fv-banner" style="border-left-color:{cor_marca}" '
        f'role="status" aria-label="{_e(alerta.id)} {_e(rotulo)}: {_e(alerta.titulo)}">'
        f'<div class="fv-banner__glifo" style="color:{cor_texto}" aria-hidden="true">{glifo}</div>'
        f'<div class="fv-banner__corpo">'
        f'<div class="fv-banner__titulo">{_e(alerta.titulo)} '
        f'<span style="color:{cor_texto};font-weight:400">({_e(rotulo)})</span></div>'
        f'<div class="fv-banner__detalhe">{_e(alerta.detalhe)}</div>{entidades}</div>'
        f"{acao}</div>"
    )


def banner_alerta(
    alertas: Sequence[Alerta],
    *,
    maximo: int = 3,
    tema: Tema = "claro",
    estado: Literal["normal", "carregando", "erro"] = "normal",
    data_ref: date | None = None,
    regras_avaliadas: int | None = None,
) -> None:
    """Banner de alertas: no maximo ``maximo`` na tela, o resto num expander.

    Ordem: ``critico`` → ``atencao``, depois por impacto (quantidade de entidades
    em nivel vermelho) desc. Vinte badges vermelhos ensinam o usuario a ignorar
    badges -- por isso o corte.

    Estados: ``carregando`` (esqueleto de uma linha), ``erro`` (nivel neutro,
    ``nao foi possivel avaliar os alertas``) e o estado vazio, que e **uma linha
    discreta**, nao um card.
    """
    if estado == "carregando":
        st.markdown(
            f'<div class="fv-banner fv-banner--linha" style="border-left-color:'
            f'{theme.cor_nivel("neutro", tema)}">'
            f'<div class="fv-esqueleto" style="height:14px;width:45%"></div></div>',
            unsafe_allow_html=True,
        )
        return
    if estado == "erro":
        cor = theme.cor_nivel("neutro", tema, uso="texto")
        st.markdown(
            f'<div class="fv-banner fv-banner--linha" style="border-left-color:{cor}">'
            f'<span style="color:{cor}">{theme.ICONE_NIVEL["neutro"]} nao foi possivel '
            f"avaliar os alertas</span></div>",
            unsafe_allow_html=True,
        )
        return
    if not alertas:
        # Pagina sem nenhuma regra nao ganha banner: um verde permanente que nunca
        # avaliou nada e falsa seguranca -- o mesmo modo de falha que escondeu um
        # alerta vermelho de ociosidade atras de "nenhum limiar atingido".
        if regras_avaliadas == 0:
            return
        cor = theme.cor_nivel("bom", tema, uso="texto")
        # "nenhum limiar atingido" era jargao: limiar e vocabulario de quem
        # construiu a regra, nao de quem le o painel.
        quando = f", em {fmt.data_br(data_ref)}" if data_ref else ""
        st.markdown(
            f'<div class="fv-banner fv-banner--linha" style="border-left-color:{cor}">'
            f'<span style="color:{cor}">{theme.ICONE_NIVEL["bom"]} Nenhum ponto de '
            f"atenção nesta página{_e(quando)}</span></div>",
            unsafe_allow_html=True,
        )
        return

    ordenados = sorted(
        alertas, key=lambda a: (_ORDEM_NIVEL.get(a.nivel, 3), -a.impacto, a.id)
    )
    visiveis, resto = ordenados[:maximo], ordenados[maximo:]
    st.markdown("".join(_linha_banner(a, tema) for a in visiveis), unsafe_allow_html=True)
    if resto:
        with st.expander(f"+ {len(resto)} outros alertas"):
            st.markdown(
                "".join(_linha_banner(a, tema) for a in resto), unsafe_allow_html=True
            )


# --------------------------------------------------------------------------
# 5.4 tabela_com_barra
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ColunaSpec:
    """Como uma coluna deve aparecer na tabela.

    ``tipo`` decide o formatador de :mod:`frotas.ui.format`; nenhuma view escreve
    ``f"{v:,.2f}"`` na mao.
    """

    rotulo: str
    tipo: Literal[
        "texto", "brl", "brl_compacto", "pct", "pp", "num", "dias", "data", "competencia", "vezes"
    ] = "texto"
    casas: int | None = None
    ajuda: str | None = None
    largura: Literal["small", "medium", "large"] | None = None


#: Largura de coluna em pixels. O ``st.dataframe`` so tem "small" (75), "medium"
#: (200) e "large" (400), e os tres desperdicam espaco: um nome de cliente de 32
#: caracteres cabe em 249 px, nao em 400. Com a soma das colunas abaixo da largura
#: do container o Streamlit distribui a sobra igualmente, entao **subestimar e
#: seguro** e superestimar e o que empurra a tabela para a rolagem horizontal.
_PX_POR_CARACTERE = 7.1
_PX_POR_CARACTERE_CABECALHO = 7.6   # cabecalho e negrito e reserva o icone de menu
_LARGURA_MINIMA = 60
_LARGURA_MAXIMA = 280


def _largura_px(rotulo: str, valores: Sequence[Any] | None = None) -> int:
    """Largura que a coluna precisa para caber cabecalho e conteudo, sem sobra."""
    largura = len(rotulo) * _PX_POR_CARACTERE_CABECALHO + 30
    if valores is not None and len(valores):
        maior = max((len(str(v)) for v in valores), default=0)
        largura = max(largura, maior * _PX_POR_CARACTERE + 22)
    return int(max(_LARGURA_MINIMA, min(_LARGURA_MAXIMA, largura)))


def _formatar_coluna(serie: pd.Series, spec: ColunaSpec) -> pd.Series:
    tipo = spec.tipo
    if tipo == "texto":
        return serie.map(lambda v: "" if fmt.eh_vazio(v) else str(v))
    if tipo == "brl":
        return serie.map(lambda v: fmt.moeda(v, 2 if spec.casas is None else spec.casas))
    if tipo == "brl_compacto":
        return serie.map(fmt.moeda_compacta)
    if tipo == "pct":
        return serie.map(lambda v: fmt.percentual(v, 1 if spec.casas is None else spec.casas))
    if tipo == "pp":
        return serie.map(lambda v: fmt.pontos_percentuais(v, 2 if spec.casas is None else spec.casas))
    if tipo == "num":
        return serie.map(fmt.contagem)
    if tipo == "dias":
        return serie.map(fmt.dias)
    if tipo == "data":
        return serie.map(fmt.data_br)
    if tipo == "competencia":
        return serie.map(lambda v: fmt.competencia(v, longo=True))
    if tipo == "vezes":
        return serie.map(fmt.vezes)
    return serie.astype(str)


def estado_vazio(titulo: str, corpo: str = "", acao: str | None = None) -> None:
    """Estado vazio da secao 6.7 do UX -- nunca uma tabela so com cabecalho."""
    corpo_html = f'<div class="fv-vazio__corpo">{_e(corpo)}</div>' if corpo else ""
    acao_html = f'<div class="fv-vazio__corpo">{_e(acao)}</div>' if acao else ""
    st.markdown(
        f'<div class="fv-vazio"><div class="fv-vazio__titulo">{_e(titulo)}</div>'
        f"{corpo_html}{acao_html}</div>",
        unsafe_allow_html=True,
    )


def tabela_com_barra(
    df: pd.DataFrame,
    *,
    colunas: Mapping[str, ColunaSpec],
    barra: str | Sequence[str] | None = None,
    pintar: Mapping[str, Sequence[str]] | None = None,
    pintar_fundo: Mapping[str, Sequence[str]] | None = None,
    tipos_barra: Mapping[str, str] | None = None,
    rotulo_barra: str | Sequence[str] | None = None,
    escala: Escala = "neutra",
    ordenar_por: str | None = None,
    crescente: bool = False,
    limite: int | None = 20,
    altura: int | None = None,
    chave: str | None = None,
    selecionavel: bool = False,
    tema: Tema = "claro",
    estado: Literal["normal", "carregando", "erro", "vazio"] = "normal",
    vazio_titulo: str = "Nenhum registro neste recorte",
    vazio_corpo: str = "",
) -> Any:
    """Tabela com barra embutida (UX 5.4).

    A barra e **sempre normalizada pelo maximo da coluna visivel**, e o maximo vai
    escrito no cabecalho (``Vencido > 30d (max R$ 480 mil)``): barra sem
    referencia mente. Os demais numeros viram texto ja formatado em pt-BR -- o
    ``format`` nativo do Streamlit nao tem separador brasileiro.

    ``escala`` escolhe a rampa: ``neutra`` por padrao; ``risco`` **so** em coluna
    de vencido/atraso/uso de limite; ``divergente`` so em desvio versus meta.

    Returns:
        O objeto de selecao do ``st.dataframe`` quando ``selecionavel=True``
        (para o drill da pagina 3), senao ``None``.
    """
    if estado == "carregando":
        st.markdown(
            "".join(
                '<div class="fv-esqueleto" style="height:28px;margin-bottom:4px"></div>'
                for _ in range(5)
            ),
            unsafe_allow_html=True,
        )
        return None
    if estado == "erro":
        st.error("Nao foi possivel carregar a tabela. As demais metricas da pagina continuam validas.")
        return None
    if estado == "vazio" or df is None or df.empty:
        estado_vazio(vazio_titulo, vazio_corpo)
        return None

    dados = df.copy()
    if ordenar_por and ordenar_por in dados.columns:
        dados = dados.sort_values(ordenar_por, ascending=crescente, na_position="last")
    if limite:
        dados = dados.head(limite)

    # ``barra=None``: tabela sem barra embutida. Uma matriz (indicador x ano) nao
    # tem uma coluna unica de magnitude para normalizar.
    # ``barra`` aceita uma coluna ou varias: cada uma vira sua propria
    # ProgressColumn, normalizada pelo **seu** maximo.
    colunas_barra: list[str] = (
        [] if barra is None else ([barra] if isinstance(barra, str) else list(barra))
    )

    saida = pd.DataFrame(index=dados.index)
    config: dict[str, Any] = {}
    for nome, spec in colunas.items():
        if nome not in dados.columns:
            continue
        saida[spec.rotulo] = _formatar_coluna(dados[nome], spec)
        config[spec.rotulo] = st.column_config.TextColumn(
            spec.rotulo, help=spec.ajuda,
            width=spec.largura or _largura_px(spec.rotulo, saida[spec.rotulo]),
        )
    # A barra e a ``ProgressColumn`` nativa, e ela sai sempre na ``primaryColor``
    # do tema -- a cor do indicador nao chega ate aqui. Ja tentamos: CSS nao
    # alcanca (o ``st.dataframe`` desenha a grade em ``<canvas>``, via
    # glide-data-grid, sem elemento no DOM para pintar) e a versao em blocos de
    # texto aceitava cor mas lia muito pior que a barra de verdade. Entre cor
    # certa e leitura boa, fica a leitura.
    for posicao, nome_col in enumerate(colunas_barra):
        if nome_col not in dados.columns:
            continue
        valores_barra = pd.to_numeric(dados[nome_col], errors="coerce")
        spec_barra = colunas.get(nome_col)
        # Coluna que ja e percentual usa a **propria escala** (0 a 100): normalizar
        # pelo maximo faria "46% da receita" aparecer como barra cheia so por ser
        # o maior da lista, o que mente sobre a grandeza.
        tipo_barra = (tipos_barra or {}).get(nome_col) or (spec_barra.tipo if spec_barra else "")
        eh_percentual = tipo_barra in ("pct", "pp")
        maximo = 100.0 if eh_percentual else (float(valores_barra.abs().max() or 0) or 1.0)
        texto_max = (
            _formatar_coluna(pd.Series([maximo]), spec_barra).iloc[0] if spec_barra
            else fmt.numero(maximo, 0)
        )
        rotulos_barra = [rotulo_barra] if isinstance(rotulo_barra, str) else list(rotulo_barra or [])
        nome_barra = (
            rotulos_barra[posicao] if posicao < len(rotulos_barra)
            else (spec_barra.rotulo if spec_barra else nome_col)
        )
        coluna_barra = f"{nome_barra} ▮"
        saida[coluna_barra] = (
            valores_barra.abs().clip(upper=100.0) if eh_percentual
            else valores_barra.abs() / maximo * 100
        ).fillna(0.0)
        ajuda_barra = (
            "Barra na escala do proprio indicador, de 0% a 100%."
            if eh_percentual
            else f"Barra normalizada pelo maior valor visivel: {texto_max}. Escala {escala}."
        )
        config[coluna_barra] = st.column_config.ProgressColumn(
            coluna_barra,
            help=ajuda_barra,
            format="%.1f%%" if eh_percentual else "%.0f%%",
            min_value=0.0,
            max_value=100.0,
            width=_largura_px(coluna_barra),
        )
    extras: dict[str, Any] = {}
    if altura:
        extras["height"] = altura
    if selecionavel:
        extras["on_select"] = "rerun"
        extras["selection_mode"] = "single-row"

    # ``pintar``: {coluna original: nivel por linha}. Serve para a coluna de
    # rating de credito, onde a cor **e** a informacao (A verde ... D vermelho).
    corpo: Any = saida
    if pintar or pintar_fundo:
        mapa = {colunas[c].rotulo: list(n) for c, n in (pintar or {}).items() if c in colunas}
        mapa_fundo = {
            colunas[c].rotulo: list(n) for c, n in (pintar_fundo or {}).items() if c in colunas
        }

        def _pintar_colunas(_: pd.DataFrame) -> pd.DataFrame:
            estilo = pd.DataFrame("", index=saida.index, columns=saida.columns)
            for rotulo, niveis in mapa.items():
                if rotulo in estilo.columns and len(niveis) == len(estilo):
                    estilo[rotulo] = [
                        f"color: {theme.cor_nivel(str(n), tema, uso='texto')}; font-weight: 600"
                        for n in niveis
                    ]
            # Fundo cheio: usado onde o valor e um rotulo curto (rating), em que a
            # celula inteira vira a marca. O texto vai na cor da superficie do
            # tema, para contrastar com a marca em qualquer nivel.
            for rotulo, niveis in mapa_fundo.items():
                if rotulo in estilo.columns and len(niveis) == len(estilo):
                    estilo[rotulo] = [
                        f"background-color: {theme.cor_nivel(str(n), tema)};"
                        f"color: {theme.tokens(tema).superficie};"
                        "font-weight: 600; text-align: center"
                        for n in niveis
                    ]
            return estilo

        corpo = saida.style.apply(_pintar_colunas, axis=None)

    return st.dataframe(
        corpo,
        column_config=config,
        hide_index=True,
        width="stretch",
        key=chave,
        **extras,
    )


def matriz_status(
    texto: pd.DataFrame,
    niveis: pd.DataFrame,
    *,
    colunas: Mapping[str, str],
    ajudas: Mapping[str, str] | None = None,
    tema: Tema = "claro",
) -> None:
    """Matriz (entidade x periodo) com a **cor** do nivel em cada celula.

    ``texto`` traz o que se le; ``niveis`` traz o nivel de cada celula, na mesma
    forma. A cor vem de ``theme.cor_nivel(..., uso="texto")``, e o glifo continua
    dentro do proprio texto: cor nunca viaja sozinha.

    Existe separado de :func:`tabela_com_barra` porque aquela formata coluna a
    coluna por tipo; aqui toda celula ja chega formatada e o que varia e a cor.
    """
    ajudas = ajudas or {}
    renomeado = texto.rename(columns=colunas)
    mapa_cor = niveis.rename(columns=colunas)

    def _pintar(_: pd.DataFrame) -> pd.DataFrame:
        estilo = pd.DataFrame("", index=renomeado.index, columns=renomeado.columns)
        for coluna in renomeado.columns:
            if coluna not in mapa_cor.columns:
                continue
            estilo[coluna] = [
                f"color: {theme.cor_nivel(str(n), tema, uso='texto')}; font-weight: 600"
                if str(n) not in ("", "neutro") else ""
                for n in mapa_cor[coluna]
            ]
        return estilo

    st.dataframe(
        renomeado.style.apply(_pintar, axis=None),
        column_config={
            rotulo: st.column_config.TextColumn(
                rotulo, help=ajudas.get(original),
                width=_largura_px(rotulo, renomeado[rotulo]
                                  if rotulo in renomeado.columns else None),
            )
            for original, rotulo in colunas.items()
        },
        hide_index=True,
        width="stretch",
    )


# --------------------------------------------------------------------------
# 5.5 seletor_data_referencia
# --------------------------------------------------------------------------

#: Texto de bloqueio da secao 6.6 do UX.
TEXTO_DATA_BLOQUEADA = (
    "Datas anteriores a 31/12/2024 nao estao disponiveis: a janela de 12 meses da "
    "inadimplencia ainda esta incompleta e o resultado seria um artefato "
    "(jan/2024 = 0,00%, mai/2024 = 8,74%)."
)


def fins_de_mes(minimo: date, maximo: date) -> list[date]:
    """Lista de fins de mes no intervalo -- toda metrica PIT do app e de fim de mes."""
    marcos = pd.date_range(start=minimo, end=maximo, freq="ME")
    datas = [d.date() for d in marcos]
    if not datas or datas[0] != minimo:
        datas = [minimo] + [d for d in datas if d != minimo]
    if maximo not in datas:
        datas.append(maximo)
    return sorted(set(datas))


def seletor_data_referencia(
    *,
    valor: date,
    minimo: date = date(2024, 12, 31),
    maximo: date = date(2026, 8, 31),
    chave: str,
    rotulo: str = "Data de referencia (independente do periodo)",
    horizontal: bool = False,
) -> date:
    """Seletor de data de referencia: lista de **fins de mes**, com presets.

    E independente do filtro de competencia, e o rotulo diz isso. Datas anteriores
    a ``minimo`` nao aparecem -- e o motivo fica escrito ao lado, nunca some em
    silencio (secao 6.6 do UX).
    """
    opcoes = fins_de_mes(minimo, maximo)
    if valor not in opcoes:
        valor = opcoes[-1]
    chave_data = f"{chave}_data"
    if chave_data not in st.session_state:
        st.session_state[chave_data] = valor
    elif st.session_state[chave_data] not in opcoes:
        st.session_state[chave_data] = opcoes[-1]

    # Um controle so. Antes eram tres para uma unica escolha: uma linha de atalhos
    # sem rotulo (que aparecia solta), o seletor, e uma legenda repetindo a data que
    # o proprio seletor ja mostrava. A lista ja abre na data mais recente, entao os
    # atalhos nao economizavam clique nenhum.
    escolhida = st.selectbox(rotulo, options=opcoes, format_func=fmt.data_br, key=chave_data)
    if horizontal:
        st.caption(TEXTO_DATA_BLOQUEADA)
    return escolhida


# --------------------------------------------------------------------------
# 5.6 rodape_proveniencia
# --------------------------------------------------------------------------



# --------------------------------------------------------------------------
# Extras de apoio (usados pelas views, sem cor ou limiar proprios)
# --------------------------------------------------------------------------


def frase(texto_html: str) -> None:
    """Paragrafo de leitura (a 'leitura em tres frases' da pagina 1).

    Recebe HTML ja montado pela view com ``<b>`` nos numeros citados; a view usa
    ``format`` para os numeros e nunca cor propria.
    """
    st.markdown(f'<div class="fv-frase">{texto_html}</div>', unsafe_allow_html=True)


def leitura_gerada(texto: str, *, rodape: str, tema: Tema = "claro") -> None:
    """Renderiza a leitura executiva aprovada, com o selo de conferencia.

    O selo nao e enfeite: ele e a razao pela qual este texto pode aparecer na
    mesma tela que os numeros conferidos. Sem ele, o leitor nao teria como
    distinguir um paragrafo escrito por um modelo de um paragrafo escrito a mao.

    O texto passa por ``_e()``: ele vem de fora do codigo e nao pode injetar HTML,
    e dois cifroes na mesma string abririam LaTeX no Markdown do Streamlit.
    """
    paragrafos = "".join(
        f"<p>{_e(trecho.strip())}</p>" for trecho in texto.split("\n") if trecho.strip()
    )
    st.markdown(
        f'<div class="fv-leitura">{paragrafos}'
        f'<span class="fv-leitura__selo">{theme.ICONE_NIVEL["bom"]} {_e(rodape)}</span></div>',
        unsafe_allow_html=True,
    )


#: Autoria e contato. Ficam aqui, e nao numa view, porque o rodape e do app.
AUTOR: str = "Ronald Martins"
PORTFOLIO: str = "rmartinsdev.com.br"
GITHUB: str = "https://github.com/ronaldmartinsx"
LINKEDIN: str = "https://www.linkedin.com/in/ronaldmartinsx/"

#: O sinal secundario da marca, `r |>`, desenhado em curvas como no Bancada:
#: nenhum glifo depende de fonte carregada, e nada aqui e cromatico.
_SINAL_MARCA = """\
<svg viewBox="0 0 94 64" height="16" role="img" aria-label="Ronald Martins" \
style="display:block">
  <rect fill="currentColor" x="11" y="20" width="4.8" height="32"/>
  <path d="M13.4 29A9.6 9.6 0 0 1 23.6 20.6" fill="none" stroke="currentColor" \
stroke-width="4.8"/>
  <rect x="38" y="20" width="4.6" height="32" fill="currentColor" opacity=".55"/>
  <path d="M54 25.5 64.5 34 54 42.5" fill="none" stroke="currentColor" \
stroke-width="4.6" opacity=".55"/>
</svg>"""

#: Glifos oficiais de GitHub e LinkedIn, copiados de
#: ``assets/icones-terceiros/`` do Bancada. O sistema e explicito: **nao
#: desenhe a mao** e **nunca use a cor de marca da plataforma** -- o azul do
#: LinkedIn seria o quarto cromatico de um sistema que tem tres. Aqui eles
#: herdam ``currentColor``, e o nome da plataforma acompanha sempre: link so
#: com icone e um alvo sem nome para leitor de tela.
_GLIFOS_PLATAFORMA: Mapping[str, str] = {
    "github": '<svg viewBox="0 0 24 24" width="13" height="13" '
              'fill="currentColor" aria-hidden="true" style="flex:none">'
              '<path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>',
    "linkedin": '<svg viewBox="0 0 448 512" width="13" height="13" '
                'fill="currentColor" aria-hidden="true" style="flex:none">'
                '<path d="M100.28 448H7.4V148.9h92.88zM53.79 108.1C24.09 108.1 0 83.5 0 53.8a53.79 53.79 0 0 1 107.58 0c0 29.7-24.1 54.3-53.79 54.3zM447.9 448h-92.68V302.4c0-34.7-.7-79.2-48.29-79.2-48.29 0-55.69 37.7-55.69 76.7V448h-92.78V148.9h89.08v40.8h1.3c12.4-23.5 42.69-48.3 87.88-48.3 94 0 111.28 61.9 111.28 142.3V448z"/></svg>',
}


def _link_plataforma(plataforma: str, href: str, rotulo: str) -> str:
    return (
        f'<a class="fv-rodape__plataforma" href="{_e(href)}" target="_blank" '
        f'rel="noopener">{_GLIFOS_PLATAFORMA[plataforma]}{_e(rotulo)}</a>'
    )


def rodape() -> None:
    """Assinatura do app: quem fez e onde encontrar.

    Chamado uma vez no entrypoint, depois de ``pagina.run()``, para aparecer em
    todas as paginas sem cada view precisar lembrar.

    Segue o ``Footer`` do Bancada: separado do conteudo por **fio**, nunca por
    inversao de fundo; mono; acromatico, porque a cor pertence ao dado.
    """
    partes = [
        f"<span><strong>{_e(AUTOR)}</strong></span>",
        f'<span><a href="https://{PORTFOLIO}" target="_blank" rel="noopener">'
        f"{_e(PORTFOLIO)}</a></span>",
        f'<span>{_link_plataforma("github", GITHUB, "GitHub")}</span>',
    ]
    partes.append(f'<span>{_link_plataforma("linkedin", LINKEDIN, "LinkedIn")}</span>')
    st.markdown(
        f'<div class="fv-rodape">'
        f'<div class="fv-rodape__linha">{"".join(partes)}</div>'
        f'<div class="fv-rodape__sinal">{_SINAL_MARCA}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def bloco_desabilitado(texto: str, *, acao: str | None = None) -> None:
    """Bloco desabilitado (secao 6.6): nao e vazio, nao e zero -- e inaplicavel."""
    estado_vazio("Bloco indisponivel neste recorte", texto, acao)


def erro_metrica(nome: str, detalhe: str | None = None) -> None:
    """Erro de uma metrica isolada (secao 6.8): as demais continuam validas."""
    st.warning(
        f"Nao foi possivel calcular {nome}. As demais metricas desta pagina continuam validas."
    )
    if detalhe:
        with st.expander("ver detalhe tecnico"):
            st.code(detalhe)


__all__ = [
    "Estado", "Unidade", "UnidadeDelta", "Escala", "Alerta", "ColunaSpec",
    "BADGES_CONHECIDOS", "NIVEL_ALERTA", "TEXTO_DATA_BLOQUEADA",
    "tema_atual", "estilos", "badge", "linha_badges", "nota_armadilha",
    "cabecalho_secao", "tile_kpi", "alertas_da_camada", "banner_alerta",
    "tabela_com_barra", "estado_vazio", "seletor_data_referencia", "fins_de_mes",
    "frase", "bloco_desabilitado", "erro_metrica",
    "rodape", "AUTOR", "PORTFOLIO",
]
