"""Pagina 0 -- Guia do Relatorio. Escrita para quem abre o relatorio hoje.

Sem grafico e sem consulta ao banco: abre instantaneo e diz, em tabela e lista,
o que cada pagina responde, como os filtros se comportam, o que entra e o que
nao entra em cada indicador, e de onde vem o dado.

E a unica pagina onde texto e o conteudo -- e ainda assim ele vem em tabela e
lista, nao em prosa corrida.
"""

from __future__ import annotations

import streamlit as st

from frotas import config
from frotas.ui import componentes as ui
from frotas.ui import format as fmt
from views import _comum as base

ctx = base.contexto()
base.abrir_pagina(ctx, "Como ler este dashboard?", secao="Guia", pagina=0, periodo_total=True)

ui.frase(
    "Este relatório responde a quatro perguntas, uma por página. Todas as páginas usam "
    "as mesmas definições de faturamento, recebimento, inadimplência e custo."
)

# --------------------------------------------------------------------------
# O que cada pagina responde
# --------------------------------------------------------------------------
ui.cabecalho_secao("O que cada página responde?")
st.markdown(
    """
| Página | A pergunta que ela responde | Em uma frase |
|---|---|---|
| **Metas** | Estamos entregando a meta? | Realizado contra o orçamento vigente, indicador por indicador e ano por ano. |
| **Faturamento e Recebimento** | Quanto faturamos e quanto entrou em caixa? | O que foi emitido por competência, o que foi efetivamente pago, e a distância entre os dois. |
| **Inadimplência** | Quanto está em aberto hoje, e com quem? | A posição da carteira numa data: quanto está vencido, há quanto tempo e de qual cliente. |
| **Custos** | Para onde vai o custo? | Composição do custo operacional por categoria, por natureza e o peso do veículo parado. |
"""
)

# --------------------------------------------------------------------------
# Como navegar
# --------------------------------------------------------------------------
ui.cabecalho_secao("Como navegar e usar os filtros?")
st.markdown(
    f"""
- **A barra lateral muda conforme a página.** Cada uma mostra só os filtros que valem
  para a análise dela, agrupados em **Quando** e **Recortes**.
- **Quando**: escolhe o intervalo de tempo. Na maioria das páginas é um período de meses;
  na de Metas é o ano do orçamento; na de Inadimplência é uma data única, porque ali a
  pergunta é "como estava a carteira naquele dia". O padrão é sempre
  {fmt.data_br(config.DATA_EXTRACAO)}, o último dia com dados.
- **Agrupar o tempo por**: nos gráficos de série, troca o eixo entre mês, trimestre e ano.
  Só isso muda, os totais do período continuam os mesmos. Não existe agrupamento por semana
  porque faturamento, custo e meta nascem mensais no sistema de origem.
- **Recortes**: segmento, porte, rating de crédito, tipo de contrato e cliente.
- **O topo da página repete os filtros em uso**, para você saber a que recorte os números
  se referem sem precisar abrir a barra lateral.
- **Cinza não é zero**: quando um bloco não se aplica ao recorte escolhido, ele aparece
  em cinza com o motivo. Cinza quer dizer "não se aplica", não "está bom".
"""
)

# --------------------------------------------------------------------------
# Definicoes
# --------------------------------------------------------------------------
ui.cabecalho_secao("O que entra em cada indicador?")
st.markdown(
    """
| Indicador | O que entra | O que **não** entra |
|---|---|---|
| **Faturamento** | Valor emitido, somado pelo **mês de competência** (o mês do serviço), antes de impostos. Inclui faturas que viriam a ser canceladas depois da data de referência. | Faturas já canceladas **naquela data**. O cancelamento é avaliado na data de referência, não pela situação atual da fatura. |
| **Recebimento** | Dinheiro que entrou, somado pela **data de pagamento**, com juros e multa. | O faturamento do mesmo mês: a defasagem típica entre emitir e receber é de 1 a 3 meses. As duas séries não somam e nunca aparecem no mesmo eixo. |
| **Inadimplência** | Valor vencido **há mais de 30 dias**, não pago e não cancelado **na data de referência**, dividido pelo faturamento bruto dos **12 meses de competência** que terminam nessa data. | Vencimentos de até 30 dias, faturas pagas e faturas canceladas até a data. Sem o corte de cancelamento na data, o indicador salta de 9,4% para 18,7%. |
| **Meta** | O orçamento **em vigor** do ano. Quando o ano ainda não fechou, a comparação usa só os meses já realizados: em agosto, o realizado de janeiro a agosto contra a meta de janeiro a agosto. | A meta do ano inteiro como base de comparação de um ano incompleto: ela faria oito meses de realizado parecerem muito abaixo do plano. |
| **Custo** | Todo o custo operacional do mês, incluindo depreciação e o custo do **veículo parado**, que não tem contrato. | Nada, mas com recorte de cliente ou de contrato o pátio sai da conta e o indicador passa a se chamar Custo de Contratos. |
"""
)

ui.nota_armadilha(
    "A carteira em aberto e a inadimplência divergem de propósito: a carteira exclui faturas "
    "baixadas, a inadimplência não. São R$ 328 mil de diferença e as duas leituras estão certas."
)

ui.nota_armadilha(
    "Este é um dataset sintético, criado para demonstração. Os nomes de cliente, os valores e "
    "as narrativas são fictícios e não representam nenhuma operação real.",
    tom="aviso",
)

