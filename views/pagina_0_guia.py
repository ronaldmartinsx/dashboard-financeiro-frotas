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
from frotas.filtros import politica_filtros
from frotas.ui import componentes as ui
from frotas.ui import format as fmt
from frotas.ui import rotulos as rot
from views import _comum as base

ctx = base.contexto()
ui.estilos(ctx.tema)
st.title("Guia do Relatório")

ui.frase(
    "Este relatório responde a quatro perguntas de negócio, uma por página. "
    "Os números saem sempre da mesma camada de definições — a mesma que o validador "
    "confere contra os valores publicados."
)

# --------------------------------------------------------------------------
# O que cada pagina responde
# --------------------------------------------------------------------------
ui.cabecalho_secao("O que cada página responde?")
st.markdown(
    """
| Página | A pergunta | Em uma frase |
|---|---|---|
| **Estamos entregando o plano?** | Metas | Realizado contra o orçamento vigente, indicador por indicador e ano por ano. |
| **Quanto faturamos e quanto entrou em caixa?** | Faturamento e recebimento | O que foi emitido por competência, o que foi efetivamente pago, e a distância entre os dois. |
| **Quanto está em aberto hoje, e com quem?** | Inadimplência | A foto da carteira numa data: quanto está vencido, há quanto tempo e de qual cliente. |
| **Para onde vai o custo?** | Custos | Composição do custo operacional por categoria, por natureza e o peso do veículo parado. |
"""
)

# --------------------------------------------------------------------------
# Como navegar
# --------------------------------------------------------------------------
ui.cabecalho_secao("Como navegar e usar os filtros?")
st.markdown(
    f"""
- **Navegação** — a lista de páginas fica na barra lateral. Este guia é a página inicial.
- **Período de competência** — move o eixo do tempo e o recorte dos fatos de faturamento
  e de custo. Os presets cobrem os últimos 12 meses, cada ano fechado e o dataset inteiro.
- **Data de referência** — é outro eixo, independente do período: define a **foto** da
  carteira. Na página de inadimplência ela fica no topo, porque lá é o controle principal.
  O padrão é {fmt.data_br(config.DATA_EXTRACAO)}, a data de extração.
- **Recortes de cliente** — segmento, porte, rating de crédito, tipo de contrato e cliente.
  Valem para faturamento, recebimento e carteira.
- **Sem dado não é zero** — quando um bloco não se aplica ao recorte, ele aparece
  desabilitado com o motivo, em cinza. Bloco cinza é "não se aplica", não é "está bom".
"""
)

ui.cabecalho_secao("Qual filtro não afeta o quê?")
st.markdown(
    """
| Filtro | Não afeta | Por quê |
|---|---|---|
| Período de competência | Inadimplência, carteira em aberto e faixas de atraso | São fotos da carteira **inteira** numa data: uma fatura de 2024 ainda vencida conta na foto de 2026. Recortar por competência esconderia justamente o atraso antigo. |
| Período de competência | O denominador da inadimplência | É sempre a janela fixa dos 12 meses anteriores à data de referência. Deixar a tela mexer nela quebraria a comparação com o número publicado. |
| Segmento, porte, rating, cliente, tipo de contrato | Custo de veículo parado | Veículo sem contrato não pertence a cliente nem a segmento. Aplicar o recorte **zeraria** o custo em vez de filtrá-lo. |
| Qualquer recorte que não seja segmento | As metas | O orçamento só existe nos níveis Empresa e Segmento. Filtrar o realizado sem filtrar a meta inventaria variação. |
| Recorte de cliente ou de contrato | Nada — mas **troca a fonte** do custo | Com o recorte, o custo passa a ser só o alocado a contrato: o pátio sai, o total encolhe e deixa de ser comparável com a meta. A página avisa quando isso acontece. |
"""
)

with st.expander("Tabela técnica de política de filtros (a mesma que a camada de dados publica)"):
    st.dataframe(rot.renomear(politica_filtros()), hide_index=True, width="stretch")

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
| **Meta** | A versão **vigente** do orçamento do ano. Em ano parcial, a comparação usa a soma das metas **dos mesmos meses** já realizados. | A versão substituída do orçamento (2026 tem duas; somar as duas dobraria o ano) e a meta do ano cheio como base de comparação de um ano incompleto. |
| **Custo** | Todo o custo operacional do mês, incluindo depreciação e o custo do **veículo parado**, que não tem contrato. | Nada — mas com recorte de cliente ou de contrato o pátio sai da conta e o indicador passa a se chamar Custo de Contratos. |
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

ui.rodape_proveniencia(
    competencia=(config.COMPETENCIA_MIN, config.COMPETENCIA_MAX),
    data_ref=config.DATA_EXTRACAO,
    versao_orcamento=ctx.versao_orcamento,
    funcoes=["filtros.politica_filtros", "metas.TIPOS_META"],
    cache_ttl=config.TTL_DIMENSOES,
    tema=ctx.tema,
)
