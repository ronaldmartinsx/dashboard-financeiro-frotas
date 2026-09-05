# Dataset Financeiro — Locadora de Frotas (sintético)

Período: **2024-01-01 a 2026-08-31** (32 meses de competência). Data de extração simulada: **2026-08-31** — nenhum pagamento existe após essa data.
Formato: CSV UTF-8, separador `,`, decimal `.`, datas ISO `YYYY-MM-DD`. Seed fixa (`20260831`) — regenerável.

## Onde os dados estao

Os CSVs foram carregados no Supabase (projeto `qoirqktsvkeyokyabpgw`, schema `public`) em 2026-08-31 e a pasta `data/` foi removida — **o banco e a fonte de verdade**. Credenciais em `.env` (`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` para leitura; `PG_DSN` para acesso direto).

Os prefixos `dim_`/`fato_`/`ponte_` sairam dos nomes (a granularidade esta no `COMMENT ON TABLE` de cada tabela):

| CSV original | Tabela no Supabase | Linhas | Mudancas de coluna |
|---|---|---|---|
| `dim_cliente.csv` | `clientes` | 58 | — |
| `dim_veiculo.csv` | `veiculos` | 245 | `taxa_locacao_mensal_pct_ativo` -> `taxa_locacao_mensal_pct`; `financiado` -> `eh_financiado` (boolean) |
| `dim_contrato.csv` | `contratos` | 153 | — |
| `ponte_contrato_veiculo.csv` | `alocacoes_veiculo` | 435 | ganhou PK `id_alocacao` + unique (contrato, veiculo, `data_alocacao`) |
| `dim_calendario.csv` | `calendario` | 1.096 | `nome_mes` -> `mes_nome`; `nome_dia_semana` -> `dia_semana`; `flag_fim_semana`/`flag_dia_util` -> booleans `eh_fim_semana`/`eh_dia_util` |
| `fato_titulos_receber.csv` | `titulos_receber` | 3.160 | `dias_atraso_pagamento` como inteiro |
| `fato_custos.csv` | `custos` | 36.298 | `id_contrato = 'SEM_ALOCACAO'` -> `NULL` (permite FK) + coluna derivada `veiculo_ocioso` |
| — (gerado) | `metas` | 2.040 | orcamento regerado por `scripts/gerar_metas.py`, sem CSV de origem (ver secao Metas) |

Em todas as tabelas, strings vazias dos CSVs viraram `NULL` — inclusive `data_pagamento`, `data_cancelamento`, `data_baixa`, `data_fim_efetiva`, `data_venda` e `data_devolucao`, onde o `NULL` carrega significado (nao pago / nao cancelado / ainda vigente). Ha FKs entre todas as tabelas, checks nos dominios enumerados e indices em `competencia`, `data_vencimento`, `data_pagamento`, `status_titulo` e `categoria_custo`. RLS habilitado com policy de SELECT para `anon` e `authenticated`; escrita fechada.

## Modelo (esquema estrela)

```
dim_calendario ──┐
                 ├── fato_titulos_receber ── dim_contrato ── dim_cliente
dim_cliente ─────┘            │                    │
                              └── fato_custos ─────┤
                                      │            │
                                 dim_veiculo ── ponte_contrato_veiculo
```

| Arquivo | Linhas | Grão |
|---|---|---|
| `fato_titulos_receber.csv` | 3.160 | 1 linha = 1 título a receber |
| `fato_custos.csv` | 36.298 | 1 linha = veículo × mês × categoria de custo |
| (gerado) | 2.040 | 1 linha = versão × métrica × granularidade × recorte |
| `dim_contrato.csv` | 153 | 1 linha = contrato de locação |
| `dim_cliente.csv` | 58 | 1 linha = cliente |
| `dim_veiculo.csv` | 245 | 1 linha = veículo |
| `ponte_contrato_veiculo.csv` | 435 | alocação veículo ↔ contrato (M:N com vigência) |
| `dim_calendario.csv` | 1.096 | 1 linha = dia (2024-01-01 a 2026-12-31) |

## Colunas relevantes

**fato_titulos_receber** — `id_titulo`, `id_contrato`, `id_cliente`, `tipo_receita` (Locação, Multa de Trânsito, KM Excedente, Avaria, Serviços Adicionais, Multa Rescisória), `competencia`, `data_emissao`, `data_vencimento`, `valor_bruto`, `valor_impostos`, `valor_liquido`, `data_pagamento`, `valor_pago`, `valor_juros_multa`, `dias_atraso_pagamento`, `status_titulo` (Pago / Em Aberto / Cancelado / Baixado), `data_cancelamento`, `motivo_cancelamento`, `data_baixa`, `valor_baixa`, `motivo_baixa` (Perda Cobrável, Glosa, Cortesia, Baixa Caixa), `forma_pagamento`.

**fato_custos** — `id_custo`, `id_veiculo`, `id_contrato` (`SEM_ALOCACAO` quando ocioso), `competencia`, `categoria_custo`, `tipo_custo` (Fixo / Variável / Não Caixa), `valor`.

**metas** — `id_meta`, `versao_meta`, `eh_versao_vigente`, `tipo_meta`, `unidade` (BRL / %), `tipo_agregacao`, `granularidade` (Mensal / Trimestral / Anual), `nivel_analise` (Empresa / Segmento), `chave_nivel` (`TOTAL` ou um valor de `clientes.segmento`), `ano`, `trimestre`, `ano_mes`, `data_inicio_periodo`, `data_fim_periodo`, `valor_meta`. Ver a secao **Metas (orcamento)** ao final.

## Regras de negócio embutidas

- **Impostos sobre receita**: 3,65% (locação pura) ou 8,65% (contratos com serviço/motorista). `valor_liquido = valor_bruto − valor_impostos`.
- **Faturamento**: emissão no 1º dia útil após o mês de competência; vencimento = emissão + prazo do contrato (10 a 45 dias).
- **Reajuste** anual na data-base do contrato (IGP-M 5,2% ou IPCA 4,3% a.a.).
- **Juros/multa**: 2% + 1% a.m. pro rata sobre títulos pagos em atraso (`valor_juros_multa`).
- **Baixa**: títulos vencidos há mais de 365 dias e não pagos viram `Baixado`, com motivo decomposto.
- **Status é "as of" 2026-08-31**. Vencido vs. a vencer deve ser calculado, nunca lido de coluna.
- **Combustível é do cliente** — não entra em `fato_custos`.

## Armadilhas plantadas de propósito

1. **Títulos cancelados (~4% do faturamento, 6% em 2025)**. Se você não aplicar filtro *point-in-time* de cancelamento, a inadimplência infla de **9,4% para 18,7%** (jun/2026). Um título cancelado em out/2025 não pode ser considerado inadimplente numa foto de dez/2025 — mas ainda estava em aberto numa foto de set/2025.
2. **Cliente em crise**: um cliente Grande para de pagar a partir de set/2025.
3. **Estresse setorial**: Construção Civil piora no 2º semestre de 2025.
4. **5 contratos com margem negativa** (frota velha + manutenção corretiva alta).
5. **Efeito base**: métricas móveis de 12 meses só estabilizam a partir de 2025 — o dataset começa em jan/2024.
6. Contratos podem começar antes de 2024 e ainda estar ativos; alguns são rescindidos antes do prazo (gera Multa Rescisória).
7. **Duas versões de orçamento para 2026**: somar sem filtrar `eh_versao_vigente` dobra o ano. A `Revisao 2026` corta o faturamento de 37,80 mi para 35,82 mi e sobe a meta de inadimplência de 6,50% para 8,00%.
8. **Metas percentuais não se somam nem se tiram média simples**: `tipo_agregacao` diz como consolidar — margem é média ponderada por `Receita Liquida`, inadimplência é valor de fim de período (o do último mês).

## Números de referência (para validar seu modelo)

| Ano | Faturamento bruto | Cancelamentos | Receita líquida | Custos | Margem |
|---|---|---|---|---|---|
| 2024 | 29,8 mi | 4,0% | 27,9 mi | 18,3 mi | 34,7% |
| 2025 | 35,0 mi | 6,0% | 32,8 mi | 21,5 mi | 34,5% |
| 2026 (8m) | 24,6 mi | 2,0% | 23,0 mi | 15,6 mi | 32,4% |

Inadimplência > 30 dias, correta (com filtro point-in-time): dez/24 3,56% · jun/25 6,47% · dez/25 10,20% · jun/26 9,37%.

Aging da carteira em 2026-08-31 (excl. cancelados e baixados): a vencer R$ 4,47 mi · 1-30d R$ 0,76 mi · 31-60d R$ 0,44 mi · 61-90d R$ 0,40 mi · 91-180d R$ 0,77 mi · 180+ R$ 0,82 mi.

## Padrões DAX de partida

```dax
Faturamento Bruto = SUM(fato_titulos_receber[valor_bruto])

-- líquido de cancelamentos, point-in-time
Faturamento Válido =
VAR DataRef = MAX(dim_calendario[data])
RETURN
CALCULATE(
    [Faturamento Bruto],
    FILTER(
        fato_titulos_receber,
        ISBLANK(fato_titulos_receber[data_cancelamento])
            || fato_titulos_receber[data_cancelamento] > DataRef
    )
)

-- inadimplência retroativa: vale para QUALQUER data de referência
Valor Vencido Retroativo =
VAR DataRef = MAX(dim_calendario[data])
VAR Carencia = 30
RETURN
CALCULATE(
    SUM(fato_titulos_receber[valor_bruto]),
    FILTER(
        ALL(fato_titulos_receber),
        fato_titulos_receber[data_vencimento] <= DataRef - Carencia
            && (ISBLANK(fato_titulos_receber[data_pagamento])
                || fato_titulos_receber[data_pagamento] > DataRef)
            && (ISBLANK(fato_titulos_receber[data_cancelamento])
                || fato_titulos_receber[data_cancelamento] > DataRef)
    )
)

Margem Operacional % =
DIVIDE(
    SUM(fato_titulos_receber[valor_liquido]) - SUM(fato_custos[valor]),
    SUM(fato_titulos_receber[valor_liquido])
)
```

Cuidado com `ALL()` na medida retroativa: ela ignora o filtro de data do calendário de propósito (a data de referência vem do contexto, não do filtro sobre os títulos). Se você relacionar `dim_calendario` a `data_vencimento`, ative essa relação como inativa e use `USERELATIONSHIP` para os cortes por vencimento.

## Perguntas que o dataset responde

- Faturamento por competência, cliente, segmento, categoria de veículo e tipo de receita; YoY 2024→2025.
- Inadimplência atual (aging) e retroativa (evolução mês a mês da mesma métrica).
- Recuperação de crédito: quanto do vencido é pago depois, e em quantos dias (`dias_atraso_pagamento`).
- Margem por contrato/veículo/categoria; contratos deficitários; impacto da manutenção corretiva por idade de frota.
- Ociosidade: custo de veículos `SEM_ALOCACAO` por mês.
- Concentração de carteira (curva ABC de clientes) e risco por rating de crédito.

## Ressalvas

Dados 100% sintéticos, gerados por processo estocástico com narrativas plantadas. Não representam a realidade de nenhuma empresa e não servem para benchmark de mercado. As correlações existem porque foram programadas — um modelo preditivo treinado aqui aprende as regras do gerador, não o comportamento real de clientes.

## Definicoes por tras dos numeros de referencia

Reproduzidos exatamente contra o banco em 2026-08-31 — as definicoes nao estavam explicitas acima:

- **Inadimplencia > 30 dias**: numerador = `valor_bruto` de titulos com `data_vencimento <= ref - 30`, nao pagos e nao cancelados *na data de referencia*; denominador = **faturamento bruto dos ultimos 12 meses de competencia**, tambem com filtro point-in-time de cancelamento. Nao e sobre a carteira vencida nem sobre o faturado acumulado.
- **Receita liquida** da tabela de referencia (27,9 / 32,8 / 23,0 mi): `sum(valor_liquido)` **incluindo** titulos cancelados — e o denominador da margem publicada. Excluindo cancelados da 26,96 / 30,74 / 22,59 mi.
- **Cancelamentos %** (4,0 / 6,0 / 2,0): contados por competencia dao 3,5 / 6,2 / 2,0 — provavelmente a referencia conta por ano de cancelamento. Os valores brutos batem; a diferenca e de definicao.
- **Aging** e **faturamento bruto** conferem casa a casa com o publicado acima.

## Metas (orcamento)

A tabela `metas` **nao veio de um CSV**. Houve um `fato_meta.csv` na raiz, feito a mao, apagado em 2026-09-01: tinha metas que nao fechavam entre granularidades (a anual excedia a soma das mensais em 1,1% a 2,6%) e cuja origem nao era reconstituivel. O orcamento foi regerado em 2026-09-01 (`scripts/gerar_metas.py`), com estas propriedades:

**Coerencia por construcao** — verificada no banco, zero divergencias:
- As 12 mensais somam exatamente as 4 trimestrais e a anual (metricas `Soma`).
- Os 8 segmentos somam exatamente o total da Empresa, em toda granularidade.
- `Margem Operacional` = (`Receita Liquida` − `Custo Operacional`) / `Receita Liquida`, reproduzivel a partir das proprias linhas da tabela.
- Indice unico parcial garante uma unica versao vigente por metrica x periodo x recorte.

**Metricas** (6): `Faturamento`, `Receita Liquida`, `Recebimento (Caixa)` — as tres com quebra por segmento; `Custo Operacional`, `Margem Operacional`, `Inadimplencia > 30d` — so no nivel Empresa, porque custo de veiculo ocioso (`custos.id_contrato` nulo) nao tem segmento a que atribuir.

**As metas nao conhecem o futuro.** Cada orcamento foi montado sobre o realizado do ano *anterior*, nunca sobre o do proprio ano — e por isso as narrativas plantadas aparecem como desvio, que e o que torna a analise de variacao interessante:

| Premissa | 2024 | 2025 | 2026 orig. | 2026 revisao |
|---|---|---|---|---|
| Faturamento alvo | 30,60 mi | +10% s/ 2024 real | +8% s/ 2025 real | orig. x 0,94 (abr-dez) |
| Margem alvo | 35,0% | 35,5% | 35,0% | 33,0% |
| Eficiencia de cobranca | 97% | 97% | 97% | 93% |
| Inadimplencia alvo (dez) | 3,0% | 3,0% | 6,5% | 8,0% |

Derivacoes: `Receita Liquida` = faturamento x 93,75% (aliquota efetiva planejada do mix 3,65%/8,65%); `Custo Operacional` = receita liquida x (1 − margem alvo), com sazonalidade de ±0,8 p.p. na margem mensal; `Recebimento (Caixa)` = eficiencia x (56% do faturado em m−1 + 30% em m−2 + 14% em m−3), a defasagem observada no realizado. Sazonalidade mensal e participacao dos segmentos vem do ano anterior, achatadas em direcao ao uniforme (orcamento nao copia o ruido do realizado). Jan/2024 tem meta de caixa zero: o razao de recebiveis do dataset comeca em jan/2024 e a primeira emissao e em fev.

A `Revisao 2026` e um reforecast de abr/2026: **jan-mar travados no realizado** (variacao zero por construcao, como em qualquer reforecast) e abr-dez revisados.

**Realizado x meta vigente** (2026 = jan-ago, contra a meta dos mesmos 8 meses):

| Ano | Faturamento | Recebimento | Margem | Inadimplencia (dez) |
|---|---|---|---|---|
| 2024 | −2,7% | −4,7% | −0,34 p.p. | +0,56 p.p. |
| 2025 | +6,8% | −2,9% | −0,98 p.p. | **+7,20 p.p.** |
| 2026 (8m) | +2,9% | +3,6% | −0,61 p.p. | +2,02 p.p. (ago) |

O grande desvio e a inadimplencia de 2025: o orcamento foi fechado em dez/2024 com o indicador em 3,56% e nao previa o cliente Grande que para de pagar em set/2025 nem o estresse da Construcao Civil. Faturamento e caixa seguiram acima do plano — a crise e de credito, nao de receita. Essa e a leitura que a tabela existe para permitir.
