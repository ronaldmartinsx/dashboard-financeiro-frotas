#!/usr/bin/env python3
"""Verifica que nenhum nome de coluna do banco vaza para a tela.

Renderiza as **cinco paginas** (e a barra lateral do entrypoint) sob
``AppTest``, coleta tudo que o usuario le como rotulo -- cabecalho de tabela,
titulo de eixo, nome de serie na legenda, titulo de colorbar, rotulo de widget e
anotacao de grafico -- e falha se algum desses textos casar com o padrao de nome
de coluna ``^[a-z][a-z0-9_]*$`` sem estar liberado em
:data:`frotas.ui.rotulos.PERMITIDOS`.

Um texto que seja **chave** de :data:`frotas.ui.rotulos.ROTULOS` tambem falha,
mesmo que nao case com o padrao: e literalmente uma coluna do banco na tela.

Uso::

    python3 scripts/verificar_rotulos.py
    python3 scripts/verificar_rotulos.py --pagina pagina_3_inadimplencia.py

Por que renderizar cada view direto, e nao navegar: **``AppTest.switch_page()``
nao funciona com ``st.navigation``** -- ele renderiza sempre a pagina inicial, e
um teste ingenuo passa cinco vezes na mesma pagina sem perceber.
``views/_comum.contexto()`` cai para ``Filtros()`` padrao quando nao ha
``session_state``, entao a view roda isolada.

Codigo de saida: 0 se nenhum rotulo vazou, 1 caso contrario.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

logging.getLogger("streamlit").setLevel(logging.ERROR)
_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAIZ))

import streamlit as st  # noqa: E402

from frotas.ui import rotulos as rot  # noqa: E402

#: As cinco paginas, na ordem da navegacao.
PAGINAS: tuple[str, ...] = (
    "pagina_0_guia.py",
    "pagina_1_metas.py",
    "pagina_2_faturamento_recebimento.py",
    "pagina_3_inadimplencia.py",
    "pagina_4_custos.py",
)

#: Rotulos de widget da barra lateral -- so aparecem rodando o entrypoint.
ENTRYPOINT = "streamlit_app.py"

VERDE, VERMELHO, AMARELO, CINZA, FIM = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"


@dataclass
class Coleta:
    """Textos de tela capturados durante o render de uma pagina."""

    cabecalhos: list[tuple[str, str]] = field(default_factory=list)   # (texto, onde)
    eixos: list[tuple[str, str]] = field(default_factory=list)
    outros: list[tuple[str, str]] = field(default_factory=list)
    #: Texto livre (legenda, markdown, expansor). Verificado por **busca dentro**
    #: da frase, nao por igualdade: "valor_bruto do vencido" nunca casaria inteiro.
    prosa: list[tuple[str, str]] = field(default_factory=list)
    #: Falhas da propria instrumentacao. Nunca podem passar em silencio: uma
    #: coleta que quebra faz o teste parecer verde sem ter olhado nada.
    problemas: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cabecalhos) + len(self.eixos) + len(self.outros) + len(self.prosa)

    def tudo(self) -> list[tuple[str, str, str]]:
        return (
            [(t, o, "cabeçalho de tabela") for t, o in self.cabecalhos]
            + [(t, o, "rótulo de eixo") for t, o in self.eixos]
            + [(t, o, "rótulo de tela") for t, o in self.outros]
        )


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _titulos_de_eixo(layout: Any) -> Iterable[tuple[str, str]]:
    """Titulo de todo eixo do layout, inclusive os de subplot (``xaxis2``...)."""
    for chave in layout:
        nome = str(chave)
        if not (nome.startswith("xaxis") or nome.startswith("yaxis")):
            continue
        eixo = layout[chave]
        titulo = _texto(getattr(getattr(eixo, "title", None), "text", None))
        if titulo:
            yield titulo, f"layout.{nome}.title"


def _da_figura(fig: Any, indice: int) -> Coleta:
    """Extrai de uma figura Plotly tudo que o leitor ve como rotulo."""
    coleta = Coleta()
    onde = f"gráfico #{indice}"
    for titulo, caminho in _titulos_de_eixo(fig.layout):
        coleta.eixos.append((titulo, f"{onde} · {caminho}"))
    titulo_legenda = _texto(getattr(getattr(fig.layout, "legend", None), "title", None)
                            and fig.layout.legend.title.text)
    if titulo_legenda:
        coleta.outros.append((titulo_legenda, f"{onde} · legenda"))
    for numero, trace in enumerate(fig.data):
        nome = _texto(getattr(trace, "name", None))
        if nome:
            coleta.outros.append((nome, f"{onde} · série {numero}"))
        barra = getattr(trace, "colorbar", None)
        titulo_barra = _texto(getattr(getattr(barra, "title", None), "text", None))
        if titulo_barra:
            coleta.outros.append((titulo_barra, f"{onde} · colorbar"))
    for anotacao in getattr(fig.layout, "annotations", ()) or ():
        texto = _texto(getattr(anotacao, "text", None))
        if texto:
            coleta.outros.append((texto, f"{onde} · anotação"))
    return coleta


def _instrumentar(coleta: Coleta) -> list[tuple[Any, str, Any]]:
    """Troca ``st.plotly_chart`` e ``st.dataframe`` por versoes que registram.

    Nao ha outra forma de ler titulo de eixo: o ``AppTest`` entrega o proto do
    grafico, nao a figura. Devolve o que precisa ser restaurado depois.
    """
    originais = [
        (st, "plotly_chart", st.plotly_chart),
        (st, "dataframe", st.dataframe),
        # Superficies de texto livre. Sem elas o verificador ficava cego justamente
        # onde o app escreve frase: foi numa dessas que o bug do cifrao-vira-LaTeX
        # sobreviveu ate um usuario reportar.
        (st, "caption", st.caption),
        (st, "markdown", st.markdown),
        (st, "expander", st.expander),
    ]
    contador = {"fig": 0, "df": 0, "txt": 0}

    def plotly_chart(figure_or_data: Any, *args: Any, **kwargs: Any) -> Any:
        contador["fig"] += 1
        try:
            parcial = _da_figura(figure_or_data, contador["fig"])
            coleta.eixos.extend(parcial.eixos)
            coleta.outros.extend(parcial.outros)
        except Exception as exc:  # noqa: BLE001 - o teste nao pode derrubar a pagina
            coleta.problemas.append(f"falha ao ler o gráfico #{contador['fig']}: {exc}")
        return originais[0][2](figure_or_data, *args, **kwargs)

    def dataframe(data: Any = None, *args: Any, **kwargs: Any) -> Any:
        contador["df"] += 1
        onde = f"tabela #{contador['df']}"
        try:
            colunas = getattr(data, "columns", None)
            # Nada de ``colunas or ()``: a verdade de um Index do pandas e ambigua
            # e o ValueError transformava a coleta inteira num silencio verde.
            if colunas is not None:
                for coluna in list(colunas):
                    coleta.cabecalhos.append((_texto(coluna), onde))
            for chave, spec in dict(kwargs.get("column_config") or {}).items():
                rotulo_col = getattr(spec, "label", None)
                if rotulo_col is None and isinstance(spec, dict):
                    rotulo_col = spec.get("label")
                coleta.cabecalhos.append((_texto(rotulo_col or chave), f"{onde} · configuração"))
        except Exception as exc:  # noqa: BLE001
            coleta.problemas.append(f"falha ao ler a tabela #{contador['df']}: {exc}")
        return originais[1][2](data, *args, **kwargs)

    def _texto_livre(bruto: Any, onde: str) -> None:
        """Registra prosa renderizada: nome de coluna, travessao e cifrao cru."""
        contador["txt"] += 1
        try:
            texto = _texto(bruto)
            if not texto:
                return
            limpo = re.sub(r"<style>.*?</style>", "", texto, flags=re.S)
            limpo = re.sub(r"<[^>]+>", " ", limpo)
            coleta.prosa.append((limpo, f"{onde} #{contador['txt']}"))
        except Exception as exc:  # noqa: BLE001
            coleta.problemas.append(f"falha ao ler texto de {onde}: {exc}")

    def caption(body: Any = "", *args: Any, **kwargs: Any) -> Any:
        _texto_livre(body, "legenda")
        return originais[2][2](body, *args, **kwargs)

    def markdown(body: Any = "", *args: Any, **kwargs: Any) -> Any:
        _texto_livre(body, "texto")
        return originais[3][2](body, *args, **kwargs)

    def expander(label: Any = "", *args: Any, **kwargs: Any) -> Any:
        _texto_livre(label, "expansor")
        return originais[4][2](label, *args, **kwargs)

    st.plotly_chart = plotly_chart  # type: ignore[assignment]
    st.dataframe = dataframe        # type: ignore[assignment]
    st.caption = caption            # type: ignore[assignment]
    st.markdown = markdown          # type: ignore[assignment]
    st.expander = expander          # type: ignore[assignment]
    return originais


def _rotulos_de_widget(at: Any, coleta: Coleta) -> None:
    """Rotulo de todo widget da pagina -- filtro tambem e nomenclatura."""
    for tipo in ("selectbox", "multiselect", "radio", "toggle", "checkbox",
                 "segmented_control", "slider", "text_input", "number_input", "button"):
        try:
            elementos = getattr(at, tipo)
        except Exception:  # noqa: BLE001 - versao do Streamlit sem esse acessor
            continue
        for elemento in elementos:
            rotulo_widget = _texto(getattr(elemento, "label", None))
            if rotulo_widget:
                coleta.outros.append((rotulo_widget, f"widget {tipo}"))


def coletar(caminho: Path) -> tuple[Coleta, list[str], float]:
    """Renderiza uma pagina e devolve (coleta, erros, segundos)."""
    import time

    from streamlit.testing.v1 import AppTest

    coleta = Coleta()
    originais = _instrumentar(coleta)
    try:
        inicio = time.time()
        at = AppTest.from_file(str(caminho), default_timeout=400)
        at.run()
        duracao = time.time() - inicio
        erros = [str(e.value) for e in at.exception] + [str(e.value) for e in at.error]
        _rotulos_de_widget(at, coleta)
    finally:
        for alvo, nome, funcao in originais:
            setattr(alvo, nome, funcao)
    return coleta, erros, duracao


#: Token de icone do Streamlit (``:material/nome:``). E markup, nao texto.
_ICONE = re.compile(r":material/[a-z0-9_]+:")

#: Palavras de bastidor que nao podem chegar a prosa da tela, com o motivo.
#: "13 em nivel vermelho e 1 em ambar" era a frase escrita por quem implementou o
#: semaforo: vermelho e ambar sao a cor da pastilha, nao o que se deve fazer.
_JARGAO: dict[str, str] = {
    "nível vermelho": "cor da pastilha, não a ação: diga o que fazer",
    "nivel vermelho": "cor da pastilha, não a ação: diga o que fazer",
    "em âmbar": "cor da pastilha, não a ação: diga o que fazer",
    "em ambar": "cor da pastilha, não a ação: diga o que fazer",
    "limiar": "termo de implementação; na tela é 'a partir de quanto'",
    "point-in-time": "termo técnico; na tela é 'na data de referência'",
    "flag": "termo técnico em inglês",
    "dataframe": "termo técnico em inglês",
}


def violacoes(coleta: Coleta) -> list[tuple[str, str, str, str]]:
    """(texto, onde, tipo, motivo) de todo rotulo que ainda e nome de coluna."""
    achados = []
    # Prosa: procura nome de coluna DENTRO da frase, e os dois defeitos que ja
    # escaparam por aqui -- travessao em texto corrido e cifrao cru (dois "$" na
    # mesma string viram formula LaTeX no Markdown do Streamlit).
    conhecidas = sorted((c for c in rot.ROTULOS if "_" in c), key=len, reverse=True)
    for bruto, onde in coleta.prosa:
        # ":material/flag:" e o nome de um icone do Streamlit, nao prosa: ele nunca
        # chega a tela como texto. Sai antes da varredura para nao acusar "flag".
        texto = _ICONE.sub(" ", bruto)
        for coluna in conhecidas:
            if re.search(rf"\b{re.escape(coluna)}\b", texto):
                achados.append((coluna, f"{onde} (dentro do texto)", "prosa",
                                "nome de coluna do banco escrito no meio da frase"))
                break
        if re.search(r"\w\s+—\s+\w", texto):
            achados.append((texto[:60], onde, "prosa",
                            "travessão em texto corrido (só format.VAZIO pode)"))
        if texto.count("$") >= 2:
            achados.append((texto[:60], onde, "prosa",
                            "dois cifrões crus: o Markdown do Streamlit vira LaTeX"))
        for termo in _JARGAO:
            if re.search(rf"\b{termo}\b", texto, re.IGNORECASE):
                achados.append((termo, onde, "prosa", _JARGAO[termo]))

    for texto, onde, tipo in coleta.tudo():
        if texto in rot.ROTULOS:
            achados.append((texto, onde, tipo, "é uma coluna do dicionário, exibida sem traduzir"))
        elif rot.parece_coluna(texto):
            achados.append((texto, onde, tipo, "casa com o padrão de nome de coluna"))
    return achados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pagina", action="append",
        help="roda so esta pagina (pode repetir); o padrao sao as cinco",
    )
    parser.add_argument(
        "--sem-entrypoint", action="store_true",
        help="pula a barra lateral do streamlit_app.py",
    )
    args = parser.parse_args()

    alvos: list[Path] = [
        _RAIZ / "views" / nome for nome in (args.pagina or PAGINAS)
    ]
    if not args.pagina and not args.sem_entrypoint:
        alvos.append(_RAIZ / ENTRYPOINT)

    print(f"Dicionário: {len(rot.ROTULOS)} colunas com rótulo, "
          f"{len(rot.VALORES)} valores de domínio traduzidos.\n")

    total_violacoes = 0
    total_rotulos = 0
    falhas_render: list[str] = []
    for caminho in alvos:
        coleta, erros, duracao = coletar(caminho)
        achados = violacoes(coleta)
        total_violacoes += len(achados)
        total_rotulos += coleta.total
        erros = erros + coleta.problemas
        marca = f"{VERMELHO}FALHOU{FIM}" if (achados or erros) else f"{VERDE}ok{FIM}"
        print(
            f"{marca}  {caminho.name:38s} {duracao:5.1f}s  "
            f"{len(coleta.cabecalhos):3d} cabeçalhos · {len(coleta.eixos):2d} eixos · "
            f"{len(coleta.outros):3d} outros rótulos"
        )
        for erro in erros:
            falhas_render.append(f"{caminho.name}: {erro}")
            print(f"   {VERMELHO}erro de render{FIM}: {erro.splitlines()[0][:160]}")
        for texto, onde, tipo, motivo in achados:
            print(f"   {VERMELHO}✗{FIM} {tipo}: {AMARELO}{texto!r}{FIM} em {onde} — {motivo}")

    print()
    if total_violacoes or falhas_render:
        print(f"{VERMELHO}FALHOU{FIM}: {total_violacoes} rótulo(s) ainda expõem nome de coluna; "
              f"{len(falhas_render)} página(s) com erro de render.")
        print(f"{CINZA}Corrija em frotas/ui/rotulos.py (ROTULOS) ou no rótulo da própria "
              f"view.{FIM}")
        return 1
    print(f"{VERDE}OK{FIM}: {total_rotulos} rótulos de tela verificados em {len(alvos)} "
          f"páginas, nenhum nome de coluna exposto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
