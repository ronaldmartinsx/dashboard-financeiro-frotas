#!/usr/bin/env python3
"""Roda todas as verificacoes do projeto e devolve 0 so se **todas** passarem.

Existe porque os verificadores rodavam a mao: nada os executava antes de um
commit, e regressao so aparecia quando alguem abria a tela. Chame este script
antes de commitar, ou ligue-o a um hook de pre-commit.

    python3 scripts/verificar_tudo.py

Cobre:

* ``pyflakes``            -- import morto, nome indefinido, f-string sem placeholder;
* ``validar_metricas``    -- a camada semantica contra os numeros publicados;
* ``verificar_rotulos``   -- nome de coluna, travessao e cifrao cru na tela;
* ``verificar_leitura``   -- o verificador de procedencia da leitura executiva
  (offline: nao chama a API nem gasta credito);
* ``verificar_tema``      -- os invariantes visuais: zero hex fora do tema,
  espelho do config.toml, contraste e daltonismo;
* render das 5 paginas    -- excecao ou ``st.error`` em qualquer uma reprova.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAGINAS = (
    "pagina_0_guia",
    "pagina_1_metas",
    "pagina_2_faturamento_recebimento",
    "pagina_3_inadimplencia",
    "pagina_4_custos",
)

VERDE, VERMELHO, CINZA, FIM = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


def _rodar(nome: str, comando: list[str]) -> tuple[bool, str]:
    inicio = time.time()
    proc = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True)
    duracao = time.time() - inicio
    ok = proc.returncode == 0
    marca = f"{VERDE}ok{FIM}" if ok else f"{VERMELHO}FALHOU{FIM}"
    print(f"  {marca}  {nome:24s} {duracao:6.1f}s")
    if not ok:
        saida = (proc.stdout + proc.stderr).strip().splitlines()
        for linha in saida[-12:]:
            print(f"      {CINZA}{linha[:150]}{FIM}")
    return ok, proc.stdout


def _paginas_renderizam() -> bool:
    """Cada view roda isolada: ``switch_page`` nao funciona com ``st.navigation``."""
    codigo = f"""
import sys, os
os.chdir({str(RAIZ)!r}); sys.path.insert(0, {str(RAIZ)!r})
from streamlit.testing.v1 import AppTest
falhas = []
for nome in {PAGINAS!r}:
    at = AppTest.from_file(f"views/{{nome}}.py", default_timeout=400)
    at.run()
    if at.exception or at.error:
        falhas.append((nome, [str(e.value)[:200] for e in (at.exception or at.error)]))
at = AppTest.from_file("streamlit_app.py", default_timeout=400)
at.run()
if at.exception:
    falhas.append(("streamlit_app", [str(e.value)[:200] for e in at.exception]))
for nome, erros in falhas:
    print(f"{{nome}}: {{erros}}")
sys.exit(1 if falhas else 0)
"""
    ok, _ = _rodar("render das páginas", [sys.executable, "-c", codigo])
    return ok


def main() -> int:
    print(f"\n{CINZA}Verificações do Dashboard Financeiro{FIM}\n")
    resultados = [
        _rodar("pyflakes", [sys.executable, "-m", "pyflakes",
                            "frotas", "views", "scripts", "streamlit_app.py"])[0],
        _rodar("validar_metricas", [sys.executable, "scripts/validar_metricas.py"])[0],
        _rodar("verificar_rotulos", [sys.executable, "scripts/verificar_rotulos.py"])[0],
        _rodar("verificar_leitura", [sys.executable, "scripts/verificar_leitura.py"])[0],
        _rodar("verificar_tema", [sys.executable, "scripts/verificar_tema.py"])[0],
        _paginas_renderizam(),
    ]
    falhas = resultados.count(False)
    print()
    if falhas:
        print(f"{VERMELHO}FALHOU{FIM}: {falhas} de {len(resultados)} verificações não passaram.")
        return 1
    print(f"{VERDE}OK{FIM}: as {len(resultados)} verificações passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
