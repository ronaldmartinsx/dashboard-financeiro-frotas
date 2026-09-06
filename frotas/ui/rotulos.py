"""Dicionario unico de nomenclatura: coluna do banco -> rotulo de executivo.

Regra do projeto: **nome de coluna nunca aparece na tela**. Nem em cabecalho de
tabela, nem em rotulo de eixo, nem em legenda, nem no expander "ver dados" --
que era a maior fonte de vazamento, porque despejava o DataFrame cru.

Os rotulos sao em portugues **com acento**, sem underscore e sem abreviacao
obscura: quem le o relatorio nao sabe (nem precisa saber) que existe uma coluna
chamada ``valor_vencido_30d``.

Uso tipico::

    from frotas.ui import rotulos

    st.dataframe(rotulos.renomear(df))                     # tabela inteira
    ui.ColunaSpec(rotulos.rotulo("nome_cliente"), "texto")  # coluna a coluna
    fig.update_yaxes(title_text=rotulos.rotulo("custo_total"))

Um mesmo rotulo pode servir a mais de uma coluna (``valor_vencido_30d`` e
``vencido_30d_mais`` sao a mesma grandeza medida por funcoes diferentes);
:func:`renomear` desambigua se as duas aparecerem no mesmo frame.

O teste ``scripts/verificar_rotulos.py`` renderiza as cinco paginas e falha se
algum cabecalho de tabela ou rotulo de eixo ainda casar com o padrao de nome de
coluna (:data:`PADRAO_COLUNA`).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

import pandas as pd

#: Padrao que identifica um nome de coluna cru (minusculas, digitos, underscore).
#: Qualquer texto de tela que case com isto e um vazamento da camada de dados.
PADRAO_COLUNA = re.compile(r"^[a-z][a-z0-9_]*$")


#: Coluna -> rotulo. Cobre as colunas devolvidas por ``frotas.metrics.*``,
#: por ``frotas.filtros.politica_filtros()`` e as colunas derivadas nas views.
ROTULOS: dict[str, str] = {
    # -- tempo -----------------------------------------------------------
    "competencia": "Competência",
    "ano_mes": "Competência",
    "ano_mes_num": "Competência (aaaammm)",
    "ano": "Ano",
    "mes": "Mês",
    "mes_nome": "Nome do Mês",
    "meses": "Meses no Período",
    "trimestre": "Trimestre",
    "data": "Data",
    "dia": "Dia",
    "dia_semana": "Dia da Semana",
    "eh_dia_util": "Dia Útil",
    "eh_fim_semana": "Fim de Semana",
    "eh_parcial": "Ano Parcial",
    "data_ref": "Data de Referência",
    "janela_ini": "Início da Janela de 12 Meses",
    "janela_fim": "Fim da Janela de 12 Meses",
    "janela_completa": "Janela de 12 Meses Completa",
    "periodo_realizado": "Período Realizado",
    "meses_realizados": "Meses Realizados",

    # -- faturamento -----------------------------------------------------
    "faturamento_bruto": "Faturamento Bruto",
    "faturamento_valido": "Faturamento Válido",
    "faturamento_bruto_12m": "Faturamento dos Últimos 12 Meses",
    "faturamento_valido_12m": "Faturamento Válido dos Últimos 12 Meses",
    "faturamento_bruto_ano_anterior": "Faturamento Bruto do Ano Anterior",
    "faturamento_bruto_ano_anterior_comparavel": "Faturamento Bruto do Ano Anterior (mesmos meses)",
    "faturamento_bruto_rateado": "Faturamento Bruto Rateado",
    "faturamento_valido_rateado": "Faturamento Válido Rateado",
    "receita_liquida": "Receita Líquida",
    "receita_liquida_ano_anterior": "Receita Líquida do Ano Anterior",
    "receita_liquida_rateada": "Receita Líquida Rateada",
    "impostos": "Impostos",
    "valor_cancelado": "Faturamento Cancelado",
    "pct_cancelado": "Cancelado sobre o Faturamento",
    "ticket_medio": "Ticket Médio",
    "qtd_titulos": "Quantidade de Faturas",
    "participacao_pct": "Participação",

    # -- recebimento -----------------------------------------------------
    "recebimento_12m": "Recebimento dos Últimos 12 Meses",
    "cobertura_pct": "Cobertura de Caixa",
    "valor_pago": "Valor Pago",
    "data_pagamento": "Pagamento",
    "forma_pagamento": "Forma de Pagamento",
    "valor_juros_multa": "Juros e Multa",

    # -- inadimplencia e carteira ----------------------------------------
    "inadimplencia_pct": "Inadimplência",
    "valor_vencido_30d": "Vencido há mais de 30 dias",
    "vencido_30d_mais": "Vencido há mais de 30 dias",
    "qtd_titulos_vencidos": "Faturas Vencidas",
    "pct_vencido_30d": "Vencido sobre o Faturamento de 12 Meses",
    "carteira_total": "Carteira em Aberto",
    "faixa": "Faixa de Atraso",
    "faixa_idade": "Faixa de Idade",
    "dias_atraso": "Dias em Atraso",
    "dias_atraso_pagamento": "Dias em Atraso",
    "dias_vencido": "Dias Vencido",
    "limite_credito": "Limite de Crédito",
    "limite_credito_total": "Limite de Crédito Total",
    "uso_limite_pct": "Uso do Limite de Crédito",
    "status_calculado": "Situação na Data de Referência",
    "status_titulo": "Situação da Fatura",
    "status_titulo_gravado": "Situação Gravada na Extração",
    "data_baixa": "Data da Baixa",
    "valor_baixa": "Valor da Baixa",
    "motivo_baixa": "Motivo da Baixa",
    "data_cancelamento": "Data do Cancelamento",
    "motivo_cancelamento": "Motivo do Cancelamento",

    # -- titulos ---------------------------------------------------------
    "id_titulo": "Fatura",
    "descricao": "Descrição",
    "data_emissao": "Emissão",
    "data_vencimento": "Vencimento",
    "valor_bruto": "Faturamento Bruto",
    "valor_liquido": "Valor Líquido",
    "valor_impostos": "Impostos",
    "tipo_receita": "Tipo de Receita",

    # -- clientes, contratos e veiculos ----------------------------------
    "id_cliente": "Código do Cliente",
    "nome_cliente": "Cliente",
    "segmento": "Segmento",
    "porte": "Porte",
    "rating_credito": "Rating de Crédito",
    "uf": "UF",
    "cidade": "Cidade",
    "qtd_clientes": "Quantidade de Clientes",
    "id_contrato": "Contrato",
    "tipo_contrato": "Tipo de Contrato",
    "status_contrato": "Situação do Contrato",
    "id_veiculo": "Veículo",
    "placa": "Placa",
    "categoria": "Categoria",
    "categoria_veiculo": "Categoria de Veículo",
    "marca_modelo": "Marca e Modelo",
    "qtd_veiculos": "Quantidade de Veículos",
    "status_veiculo": "Situação do Veículo",

    # -- custos ----------------------------------------------------------
    "custo_total": "Custo Total",
    "custo_alocado": "Custo Alocado a Contrato",
    "custo_ocioso": "Custo de Veículo Parado",
    "custo_fixo": "Custo Fixo",
    "custo_variavel": "Custo Variável",
    "custo_nao_caixa": "Custo Não Caixa",
    "custo_ocioso_incluido": "Inclui Custo de Veículo Parado",
    "escopo": "Escopo do Custo",
    "categoria_custo": "Categoria de Custo",
    "tipo_custo": "Natureza do Custo",
    "taxa_ociosidade_pct": "Taxa de Ociosidade",
    "qtd_veiculos_ociosos": "Veículos Parados",
    "qtd_veiculos_frota": "Veículos na Frota",
    "pct_do_custo_total": "Peso no Custo Total",

    # -- metas -----------------------------------------------------------
    "tipo_meta": "Indicador",
    "unidade": "Unidade",
    "tipo_agregacao": "Forma de Consolidação",
    "versao_meta": "Versão do Orçamento",
    "eh_versao_vigente": "Versão Vigente",
    "granularidade": "Granularidade",
    "nivel_analise": "Nível de Análise",
    "chave_nivel": "Recorte",
    "realizado": "Realizado",
    "meta": "Meta",
    "meta_alinhada": "Meta dos Mesmos Meses",
    "meta_anual": "Meta do Ano Cheio",
    "meta_comparavel": "Meta Comparável",
    "valor_meta_anual": "Meta do Ano Cheio",
    "base_comparacao": "Base da Comparação",
    "variacao_abs": "Desvio Absoluto (R$ ou p.p.)",
    "variacao_pct": "Desvio Relativo",
    "variacao_abs_alinhada": "Desvio Absoluto nos Mesmos Meses",
    "variacao_pct_alinhada": "Desvio Relativo nos Mesmos Meses",
    "variacao_abs_anual": "Desvio Absoluto sobre o Ano Cheio",
    "variacao_pct_anual": "Desvio Relativo sobre o Ano Cheio",
    "variacao_pct_comparavel": "Variação sobre os Mesmos Meses do Ano Anterior",

    # -- alertas ---------------------------------------------------------
    "id": "Código",
    "pagina": "Página",
    "titulo": "Título",
    "nivel": "Nível",
    "valor": "Valor",
    "limiar_ambar": "Limiar de Atenção",
    "limiar_vermelho": "Limiar Crítico",
    "ambar": "Limiar de Atenção",
    "vermelho": "Limiar Crítico",
    "direcao": "Direção",
    "qtd_vermelho": "Entidades em Nível Crítico",
    "qtd_ambar": "Entidades em Atenção",
    "entidades": "Entidades",
    "detalhe": "Detalhe",
    "regra": "Regra",

    # -- politica de filtros ---------------------------------------------
    "metrica": "Indicador",
    "filtros_ignorados": "Filtros que não se aplicam",
    "motivo": "Por que não se aplica",

    # -- colunas derivadas nas views -------------------------------------
    "magnitude": "Magnitude do Desvio",
    "share": "Participação",
    "desvio": "Desvio",
    "peso": "Peso",
}


#: Faixas de aging: viram coluna em ``credito.aging_por_cliente`` e categoria em
#: ``credito.aging_carteira``. Nao casam com :data:`PADRAO_COLUNA`, mas
#: ``180+d`` tambem nao e portugues.
FAIXAS_AGING: dict[str, str] = {
    "A vencer": "A vencer",
    "1-30d": "1 a 30 dias",
    "31-60d": "31 a 60 dias",
    "61-90d": "61 a 90 dias",
    "91-180d": "91 a 180 dias",
    "180+d": "Mais de 180 dias",
}

#: Escopo do custo (``custos.*``) traduzido para a tela.
ESCOPO_CUSTO: dict[str, str] = {
    "empresa": "Empresa (inclui veículo parado)",
    "contratos": "Somente contratos",
}

#: **Valores** de dominio. O banco guarda tudo sem acento ("Construcao Civil",
#: "Manutencao Corretiva"); a tela mostra portugues. A cor de segmento continua
#: sendo resolvida pelo valor **cru** -- traduza so na hora de escrever o rotulo.
#:
#: ``Margem Operacional`` esta ausente de proposito: ela saiu do escopo e nao
#: pode ganhar rotulo de tela. Se aparecer aqui algum dia, apareceu por engano.
VALORES: dict[str, str] = {
    # metas
    "Receita Liquida": "Receita Líquida",
    "Inadimplencia > 30d": "Inadimplência acima de 30 dias",
    "Fim de Periodo": "Valor do último mês do período",
    "Soma": "Soma dos meses",
    "Orcamento Original": "Orçamento Original",
    "Revisao 2026": "Revisão 2026",
    "BRL": "R$",
    # segmentos
    "Agronegocio": "Agronegócio",
    "Construcao Civil": "Construção Civil",
    "Industria": "Indústria",
    "Logistica e Transporte": "Logística e Transporte",
    "Mineracao": "Mineração",
    "Servicos Publicos": "Serviços Públicos",
    "Varejo e Distribuicao": "Varejo e Distribuição",
    # porte
    "Medio": "Médio",
    # contratos
    "Locacao com Motorista": "Locação com Motorista",
    "Locacao Mensal Frota": "Locação Mensal de Frota",
    "Locacao Spot": "Locação Spot",
    "Terceirizacao de Frota": "Terceirização de Frota",
    # veiculos
    "Automovel Executivo": "Automóvel Executivo",
    "Caminhao Munck": "Caminhão Munck",
    "Caminhao Toco": "Caminhão Toco",
    "Caminhao Truck": "Caminhão Truck",
    "Cavalo Mecanico": "Cavalo Mecânico",
    "Onibus Rodoviario": "Ônibus Rodoviário",
    "Van / Furgao": "Van / Furgão",
    # receita
    "Locacao": "Locação",
    "Multa de Transito": "Multa de Trânsito",
    "Multa Rescisoria": "Multa Rescisória",
    "Servicos Adicionais": "Serviços Adicionais",
    # cancelamento e baixa
    "Erro de Emissao": "Erro de Emissão",
    "Renegociacao de Contrato": "Renegociação de Contrato",
    "Troca de Veiculo": "Troca de Veículo",
    "Perda Cobravel": "Perda Cobrável",
    # custos
    "Depreciacao": "Depreciação",
    "Manutencao Corretiva": "Manutenção Corretiva",
    "Manutencao Preventiva": "Manutenção Preventiva",
    "Motorista (Mao de Obra)": "Motorista (Mão de Obra)",
    "Patio e Ociosidade": "Pátio e Ociosidade",
    "Variavel": "Variável",
    "Nao Caixa": "Não Caixa",
    # alertas
    "ok": "Dentro do limiar",
    "ambar": "Atenção",
    "vermelho": "Crítico",
    "indisponivel": "Não se aplica ao recorte",
}

#: Colunas cujo **conteudo** e um valor de dominio -- :func:`renomear` traduz as
#: celulas destas colunas com :func:`valor`.
COLUNAS_DE_DOMINIO: frozenset[str] = frozenset({
    "tipo_meta", "tipo_agregacao", "unidade", "versao_meta",
    "segmento", "porte", "rating_credito", "tipo_contrato", "status_contrato",
    "categoria", "categoria_veiculo", "tipo_receita",
    "categoria_custo", "tipo_custo",
    "motivo_cancelamento", "motivo_baixa", "forma_pagamento",
    "status_titulo", "status_titulo_gravado", "status_calculado", "nivel",
})

#: Todos os textos que a UI pode exibir mesmo casando com o padrao de coluna.
#: Hoje esta vazio de proposito: nenhum rotulo legivel se parece com uma coluna.
PERMITIDOS: frozenset[str] = frozenset()


def rotulo(coluna: str, padrao: str | None = None) -> str:
    """Rotulo legivel de uma coluna.

    Args:
        coluna: nome da coluna como vem de ``frotas.metrics.*``.
        padrao: texto a devolver quando a coluna nao esta no dicionario. Sem
            ele, devolve uma versao apresentavel (underscore vira espaco e a
            primeira letra sobe) -- que ainda assim **nao** casa com
            :data:`PADRAO_COLUNA`, entao um esquecimento aparece na tela como
            texto estranho, nunca como nome tecnico silencioso.
    """
    nome = str(coluna)
    if nome in ROTULOS:
        return ROTULOS[nome]
    if padrao is not None:
        return padrao
    return nome.replace("_", " ").strip().capitalize() or nome


def faixa_aging(bruto: Any) -> str:
    """Rotulo de uma faixa de aging (``'180+d'`` -> ``'Mais de 180 dias'``)."""
    return FAIXAS_AGING.get(str(bruto), str(bruto))


def escopo_custo(bruto: Any) -> str:
    """Rotulo do escopo do custo (``'contratos'`` -> ``'Somente contratos'``)."""
    return ESCOPO_CUSTO.get(str(bruto), str(bruto))


def valor(bruto: Any) -> str:
    """Rotulo de um **valor** de dominio (``'Construcao Civil'`` -> com cedilha).

    O banco guarda os dominios sem acento. Use esta funcao ao escrever o rotulo
    na tela e **mantenha o valor cru** para procurar cor
    (``theme.cor_segmento``) ou para comparar com o dominio.
    """
    if bruto is None or (isinstance(bruto, float) and bruto != bruto):
        return ""
    texto = str(bruto)
    return VALORES.get(texto, FAIXAS_AGING.get(texto, ESCOPO_CUSTO.get(texto, texto)))


def valores(brutos: Iterable[Any]) -> list[str]:
    """:func:`valor` aplicado a uma sequencia -- rotulos de eixo categorico."""
    return [valor(b) for b in brutos]


def renomear(
    df: pd.DataFrame | None,
    *,
    extras: Mapping[str, str] | None = None,
    apenas: Iterable[str] | None = None,
    traduzir_faixas: bool = True,
) -> pd.DataFrame:
    """Devolve uma copia do frame com as colunas ja em linguagem de negocio.

    E o que o expander "ver dados" usa: sem isto, ele publica o esquema do banco.

    Args:
        df: frame vindo da camada semantica.
        extras: sobrescritas pontuais (``{"categoria": "Categoria de Veículo"}``)
            para colunas cujo rotulo depende do contexto.
        apenas: se informado, mantem so estas colunas, nesta ordem.
        traduzir_faixas: tambem traduz os **valores** das colunas de dominio
            (segmento, categoria de custo, faixa de atraso, escopo...), que o
            banco guarda sem acento.

    Colunas distintas que compartilham rotulo recebem sufixo numerado, para o
    frame nao ficar com dois cabecalhos iguais.
    """
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    saida = df.copy()
    if apenas is not None:
        colunas = [c for c in apenas if c in saida.columns]
        saida = saida[colunas]
    mapa = dict(extras or {})
    usados: dict[str, int] = {}
    novos: list[str] = []
    originais = list(saida.columns)
    for coluna in originais:
        texto = mapa.get(str(coluna)) or rotulo(str(coluna))
        usados[texto] = usados.get(texto, 0) + 1
        novos.append(texto if usados[texto] == 1 else f"{texto} ({usados[texto]})")
    saida.columns = novos
    if traduzir_faixas:
        for original, novo in zip(originais, novos):
            if original == "faixa":
                saida[novo] = saida[novo].map(faixa_aging)
            elif original == "escopo":
                saida[novo] = saida[novo].map(escopo_custo)
            elif original in COLUNAS_DE_DOMINIO:
                saida[novo] = saida[novo].map(valor)
    return saida


def parece_coluna(texto: Any) -> bool:
    """``True`` quando o texto tem cara de nome de coluna e nao esta liberado."""
    valor = str(texto).strip()
    if not valor or valor in PERMITIDOS:
        return False
    return bool(PADRAO_COLUNA.match(valor))


__all__ = [
    "PADRAO_COLUNA", "ROTULOS", "FAIXAS_AGING", "ESCOPO_CUSTO", "VALORES",
    "COLUNAS_DE_DOMINIO", "PERMITIDOS",
    "rotulo", "faixa_aging", "escopo_custo", "valor", "valores", "renomear",
    "parece_coluna",
]
