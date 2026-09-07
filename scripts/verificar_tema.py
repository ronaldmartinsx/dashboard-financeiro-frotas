"""Verifica os invariantes visuais do app. Roda offline, sem rede e sem banco.

Ate agora estes invariantes eram apenas **declarados** no README: "a UI nao
inventa cor", "todo hex nasce em theme.py", "o config.toml e espelho fiel do
tema". Declaracao sem verificacao apodrece -- e o `config.toml` ja tinha ficado
fora de sincronia mais de uma vez sem ninguem notar, porque nada avisava.

Cinco portoes:

1. **Zero hex fora do tema.** Nenhuma cor literal em ``views/``, no restante de
   ``frotas/`` ou no entrypoint.
2. **Espelho.** Os valores do ``.streamlit/config.toml`` batem com os tokens.
3. **Contraste.** Cada cor de texto alcanca 4,5:1 e cada cor de marca 3:1 contra
   a superficie, os pisos da WCAG que o projeto adotou.
4. **Rotulo direto.** ``_BAIXO_CONTRASTE`` lista exatamente os matizes medidos
   abaixo de 3:1 -- nem a mais, nem a menos.
5. **Daltonismo.** Os cinco indicadores continuam distinguiveis sob deuteranopia
   e protanopia, simuladas com a matriz que o proprio Bancada publica.

    python3 scripts/verificar_tema.py
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from frotas.ui import theme  # noqa: E402

VERDE, VERMELHO, CINZA, FIM = "\033[32m", "\033[31m", "\033[90m", "\033[0m"

#: Piso de contraste. Texto segue a WCAG AA; marca segue 1.4.11 (componente).
PISO_TEXTO = 4.5
PISO_MARCA = 3.0

#: Separacao minima entre dois matizes simulados, em distancia CIE76. O projeto
#: adotou 8 quando validou a paleta antiga; o alvo continua o mesmo.
PISO_DALTONISMO = 8.0

#: Matrizes de simulacao. A de deuteranopia e a que o Bancada publica em
#: ``guidelines/dados-paleta.card.html`` como prova viva da paleta.
_SIMULACAO = {
    "deuteranopia": ((0.625, 0.375, 0.0), (0.700, 0.300, 0.0), (0.0, 0.300, 0.700)),
    "protanopia": ((0.567, 0.433, 0.0), (0.558, 0.442, 0.0), (0.0, 0.242, 0.758)),
}


def _rgb(hex_cor: str) -> tuple[float, float, float]:
    h = hex_cor.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _luminancia(hex_cor: str) -> float:
    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _rgb(hex_cor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(frente: str, fundo: str) -> float:
    a, b = _luminancia(frente), _luminancia(fundo)
    claro, escuro = max(a, b), min(a, b)
    return (claro + 0.05) / (escuro + 0.05)


def _lab(hex_cor: str) -> tuple[float, float, float]:
    """sRGB -> CIE Lab (D65), para medir distancia perceptual."""
    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _rgb(hex_cor))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def distancia(a: str, b: str) -> float:
    la, lb = _lab(a), _lab(b)
    return sum((x - y) ** 2 for x, y in zip(la, lb)) ** 0.5


def simular(hex_cor: str, tipo: str) -> str:
    m = _SIMULACAO[tipo]
    r, g, b = _rgb(hex_cor)
    saida = []
    for linha in m:
        v = sum(c * p for c, p in zip((r, g, b), linha))
        saida.append(max(0, min(255, round(v * 255))))
    return "#" + "".join(f"{c:02X}" for c in saida)


# --------------------------------------------------------------------------

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_RGBA = re.compile(r"\brgba?\(")


class Relatorio:
    def __init__(self) -> None:
        self.falhas: list[str] = []

    def afirmar(self, secao: str, o_que: str, ok: bool, detalhe: str = "") -> None:
        marca = f"{VERDE}ok{FIM}" if ok else f"{VERMELHO}FALHA{FIM}"
        extra = f"  {CINZA}{detalhe}{FIM}" if detalhe else ""
        print(f"  {marca}  {o_que:54}{extra}")
        if not ok:
            self.falhas.append(f"[{secao}] {o_que}: {detalhe}")


def verificar_hex_literal(rel: Relatorio) -> None:
    """Nenhuma cor escrita na mao fora de theme.py."""
    alvos = sorted(
        [p for p in (RAIZ / "views").rglob("*.py")]
        + [p for p in (RAIZ / "frotas").rglob("*.py") if p.name != "theme.py"]
        + [RAIZ / "streamlit_app.py"]
    )
    culpados = []
    for caminho in alvos:
        for n, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
            sem_comentario = linha.split("#")[0] if not linha.lstrip().startswith("#") else ""
            if _HEX.search(sem_comentario) or _RGBA.search(sem_comentario):
                culpados.append(f"{caminho.relative_to(RAIZ)}:{n}")
    rel.afirmar("hex", "nenhum hex literal fora de theme.py", not culpados,
                ", ".join(culpados[:4]) if culpados else f"{len(alvos)} arquivos varridos")


def verificar_espelho(rel: Relatorio) -> None:
    """O config.toml repete os tokens, e nada avisava quando divergia."""
    cfg = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    tema_cfg = cfg.get("theme", {})
    t = theme.tokens()
    esperado = {
        "backgroundColor": t.superficie,
        "secondaryBackgroundColor": t.plano,
        "textColor": t.tinta,
        "primaryColor": theme.PALETA_DADOS[0],
        "borderColor": t.grade,
        "redColor": t.marca_critico,
        "greenColor": t.marca_bom,
        "yellowColor": t.marca_atencao,
        "orangeColor": t.marca_serio,
        "grayTextColor": t.texto_neutro,
    }
    divergentes = [
        f"{chave}={tema_cfg.get(chave)} != {valor}"
        for chave, valor in esperado.items()
        if str(tema_cfg.get(chave, "")).upper() != valor.upper()
    ]
    rel.afirmar("espelho", "config.toml espelha os tokens", not divergentes,
                "; ".join(divergentes[:3]) if divergentes else f"{len(esperado)} chaves conferidas")

    paleta_cfg = [c.upper() for c in tema_cfg.get("chartCategoricalColors", [])]
    rel.afirmar("espelho", "config.toml traz a paleta categorica na ordem",
                paleta_cfg == [c.upper() for c in theme.PALETA_DADOS],
                f"{len(paleta_cfg)} matizes")

    seq_cfg = [c.upper() for c in tema_cfg.get("chartSequentialColors", [])]
    rel.afirmar("espelho", "config.toml traz a rampa sequencial",
                seq_cfg == [c.upper() for c in theme.RAMPA_NEUTRA],
                f"{len(seq_cfg)} passos")


def verificar_contraste(rel: Relatorio) -> None:
    t = theme.tokens()
    fundo = t.superficie
    textos = {
        "tinta": t.tinta, "tinta_secundaria": t.tinta_secundaria,
        "tinta_fraca": t.tinta_fraca,
        "texto_bom": t.texto_bom, "texto_atencao": t.texto_atencao,
        "texto_serio": t.texto_serio, "texto_critico": t.texto_critico,
        "texto_neutro": t.texto_neutro,
    }
    piores = [f"{n} {contraste(c, fundo):.2f}:1"
              for n, c in textos.items() if contraste(c, fundo) < PISO_TEXTO]
    rel.afirmar("contraste", f"cor de texto alcanca {PISO_TEXTO}:1", not piores,
                "; ".join(piores) if piores
                else f"pior: {min(contraste(c, fundo) for c in textos.values()):.2f}:1")

    marcas = {
        "marca_bom": t.marca_bom, "marca_atencao": t.marca_atencao,
        "marca_serio": t.marca_serio, "marca_critico": t.marca_critico,
        "marca_neutro": t.marca_neutro, "eixo": t.eixo,
    }
    fracas = [f"{n} {contraste(c, fundo):.2f}:1"
              for n, c in marcas.items() if contraste(c, fundo) < PISO_MARCA]
    rel.afirmar("contraste", f"cor de marca alcanca {PISO_MARCA}:1", not fracas,
                "; ".join(fracas) if fracas
                else f"pior: {min(contraste(c, fundo) for c in marcas.values()):.2f}:1")

    # A celula de rating pinta o fundo com a marca e escreve na superficie: e um
    # desvio deliberado da regra "sinal como veu", entao o contraste do par tem
    # que ser medido, nao presumido.
    ruins = []
    for nota, nivel in theme.RATING_NIVEL.items():
        razao = contraste(theme.cor_nivel(nivel), t.superficie)
        if razao < PISO_MARCA:
            ruins.append(f"rating {nota} {razao:.2f}:1")
    rel.afirmar("contraste", "celula de rating legivel em bloco cheio", not ruins,
                "; ".join(ruins) if ruins else "A a D conferidos")


def verificar_rotulo_direto(rel: Relatorio) -> None:
    """_BAIXO_CONTRASTE tem que ser exatamente o que a medicao diz."""
    t = theme.tokens()
    medido = {c.upper() for c in theme.PALETA_DADOS
              if contraste(c, t.superficie) < PISO_MARCA}
    declarado = {c.upper() for c in theme._BAIXO_CONTRASTE}
    detalhe = ", ".join(f"{c} {contraste(c, t.superficie):.2f}:1" for c in sorted(medido))
    rel.afirmar("alivio", "_BAIXO_CONTRASTE bate com a medicao", medido == declarado,
                detalhe if medido == declarado
                else f"medido {sorted(medido)} != declarado {sorted(declarado)}")


def verificar_daltonismo(rel: Relatorio) -> None:
    """Os cinco indicadores continuam distinguiveis sem percepcao de vermelho/verde."""
    cores = [(nome, theme.cor_indicador(nome)) for nome, _ in theme.INDICADORES]
    for tipo in _SIMULACAO:
        pior, par = float("inf"), ("", "")
        for i in range(len(cores)):
            for j in range(i + 1, len(cores)):
                d = distancia(simular(cores[i][1], tipo), simular(cores[j][1], tipo))
                if d < pior:
                    pior, par = d, (cores[i][0], cores[j][0])
        rel.afirmar("daltonismo", f"indicadores separados em {tipo}", pior >= PISO_DALTONISMO,
                    f"pior par {par[0]} x {par[1]}: {pior:.1f} (piso {PISO_DALTONISMO:.0f})")


def main() -> int:
    print(f"{CINZA}Invariantes visuais{FIM}\n")
    rel = Relatorio()
    verificar_hex_literal(rel)
    verificar_espelho(rel)
    verificar_contraste(rel)
    verificar_rotulo_direto(rel)
    verificar_daltonismo(rel)
    print()
    if rel.falhas:
        print(f"{VERMELHO}FALHOU{FIM}: {len(rel.falhas)} invariante(s) quebrado(s).")
        for f in rel.falhas:
            print(f"  - {f}")
        return 1
    print(f"{VERDE}OK{FIM}: os invariantes visuais valem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
