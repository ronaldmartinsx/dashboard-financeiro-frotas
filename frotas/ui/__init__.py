"""Camada de apresentacao compartilhada: tema, formatacao e componentes.

Tres modulos, tres responsabilidades, nenhuma regra de negocio:

* :mod:`frotas.ui.theme` -- tokens de cor (claro/escuro), paletas nomeadas e os
  helpers que traduzem "limiar de alerta" em cor. Sem Streamlit.
* :mod:`frotas.ui.format` -- formatacao pt-BR (moeda, percentual, pontos
  percentuais, competencia, contagem, delta). Sem Streamlit, sem ``locale``.
* :mod:`frotas.ui.rotulos` -- o dicionario unico coluna -> rotulo de executivo.
  Nome de coluna do banco nao aparece na tela; quem traduz e este modulo.

A especificacao visual completa (wireframes, microcopy, regras de interacao)
esta em ``docs/03_ux.md``. Este pacote e a parte executavel dela.
"""

from frotas.ui import format, rotulos, theme

__all__ = ["theme", "format", "rotulos"]
