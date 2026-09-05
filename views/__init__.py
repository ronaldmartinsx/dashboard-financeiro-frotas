"""Paginas do app -- uma por arquivo, alvo de ``st.Page`` em ``streamlit_app.py``.

Um guia e quatro perguntas, uma por pagina, declaradas no proprio titulo:

0. ``pagina_0_guia``                     Guia do Relatorio
1. ``pagina_1_metas``                    Estamos entregando a meta?
2. ``pagina_2_faturamento_recebimento``  Quanto faturamos e quanto entrou em caixa?
3. ``pagina_3_inadimplencia``            Quanto esta em aberto hoje, e com quem?
4. ``pagina_4_custos``                   Para onde vai o custo?

``_comum`` nao e pagina: e o andaime compartilhado (contexto, carregamento em
paralelo, faixa de KPIs e utilitarios de grafico).

Duas regras editoriais que valem para as quatro paginas de numeros:

* **no maximo um bloco curto de texto explicativo por pagina** (2 a 3 linhas).
  O que precisa ser dito para interpretar um numero vira **nota de rodape do
  visual**, rotulo, anotacao no grafico ou tooltip -- nunca paragrafo repetindo
  o que o grafico ja mostra;
* **nenhum nome de coluna do banco aparece na tela**: cabecalho, eixo, legenda e
  o expander "ver dados" passam por :mod:`frotas.ui.rotulos`.
"""
