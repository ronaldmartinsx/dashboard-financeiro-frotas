# 01 — Definicao de negocio, KPIs e estrutura do app

**Autor:** Lider de Negocios e KPIs · **Data:** 2026-09-01 · **Fonte:** Supabase `public`, leitura direta (PG_DSN)
**Data de referencia do dataset:** `2026-08-31` (`REF`). Competencias de `2024-01-01` a `2026-08-01`.
**Pre-requisitos:** `docs/00_briefing_tecnico.md` (esquema) e `DICIONARIO_DADOS.md` (regras). Este documento e a fonte
de verdade das **metricas**: nome, formula, granularidade, armadilha e meta comparavel.

Todos os numeros abaixo foram apurados por SQL contra o banco em 2026-09-01. Nenhum foi estimado.

---

## 1. Sumario executivo

A empresa **vende mais do que planejou e recebe quase o que planejou — e esta perdendo o controle do credito.**

- **Receita acima do plano, todos os anos.** Faturamento bruto 29,79 mi (2024) · 35,02 mi (2025) · 24,62 mi (2026, 8m).
  Contra a meta vigente: **−2,7% · +6,8% · +2,9%**. Caixa: **−4,7% · −2,9% · +3,6%**. Nao ha problema de demanda.
- **A crise e de credito e comeca em out/2025.** A inadimplencia > 30d (point-in-time) sai de **6,92% em set/2025**
  para **9,79% em out/2025** e **10,29% em nov/2025** — um salto de **+3,37 p.p. em dois meses**, R$ 1,17 mi de novo
  vencido. Fecha 2025 em **10,20%** contra meta de **3,00%**: **+7,20 p.p.**, o maior desvio do dataset. Em ago/2026
  ainda esta em **10,02%**, contra meta de **8,80%** no mes (+1,22 p.p.).
- **Tres focos explicam o salto.** (a) **Servicos Manicore S.A. 001** (Grande, Agronegocio, rating C): zero vencido ate
  set/2025, R$ 53 mil vencidos em out/2025 e **nunca mais volta a zero** — R$ 159,5 mil vencidos em ago/2026, atrasos
  de 70 a 119 dias, 24,4% do proprio faturamento 12m parado. Impacto acumulado vs. seu proprio historico: **R$ 245 mil**.
  (b) **Construcao Civil**: inadimplencia de 5,32% (dez/24) → **11,85% (jun/25)** → **20,24% (dez/25)** → 18,07% (ago/26);
  o segmento e **14,2% do faturamento 12m mas 25,6% do vencido**. (c) **Logistica e Transporte**, por tamanho: 40,3% da
  receita e 35,2% do vencido (R$ 1,24 mi).
- **A margem cai, mas por custo, nao por preco.** 34,66% (2024) → 34,52% (2025) → **32,39% (2026, 8m)**. Manutencao
  corretiva custa **R$ 8,9 mil/veiculo-ano** na frota de 0-2 anos e **R$ 23,2 mil** na de 7+ anos (2,6x); nos veiculos
  7+ anos ela e **29,5% do custo total** contra 9,2% nos novos.
- **Ociosidade dobrou.** Custo de veiculo ocioso: R$ 297 mil (2024) · R$ 357 mil (2025) · **R$ 434 mil em 8 meses de
  2026** (anualizado, +82% sobre 2025). Em ago/2026, **15 de 239 veiculos (6,3%)** estavam sem contrato.
- **Concentracao moderada, risco concentrado.** 12 clientes (classe A) = **49,1%** do faturamento 12m; os 5 maiores
  devedores = **33,2%** do vencido; ratings C e D = **70,8%** do vencido. **13 clientes estao com exposicao em aberto
  acima do proprio limite de credito** (o pior, Agropecuaria Trombetas 028, a **283%**).

---

## 2. Validacao dos numeros de referencia

Metodo: SQL direto, sem cache, sem arredondamento intermediario. `REF = 2026-08-31`.

### 2.1 Bateram exatamente

| Metrica | Publicado | Apurado | Def. que reproduz |
|---|---|---|---|
| Faturamento bruto 2024 / 2025 / 2026(8m) | 29,8 / 35,0 / 24,6 mi | **29,787 / 35,023 / 24,624 mi** | `sum(valor_bruto)` por `year(competencia)`, **sem** filtro de cancelamento |
| Receita liquida 2024 / 2025 / 2026(8m) | 27,9 / 32,8 / 23,0 mi | **27,949 / 32,784 / 23,050 mi** | `sum(valor_liquido)` **incluindo cancelados** |
| Custos 2024 / 2025 / 2026(8m) | 18,3 / 21,5 / 15,6 mi | **18,263 / 21,469 / 15,583 mi** | `sum(custos.valor)`, **inclui** ocioso (`id_contrato is null`) |
| Margem 2024 / 2025 / 2026(8m) | 34,7 / 34,5 / 32,4% | **34,66 / 34,52 / 32,39%** | `(RL_incl_canc − custo_total) / RL_incl_canc` |
| Inadimplencia dez/24 · jun/25 · dez/25 · jun/26 | 3,56 / 6,47 / 10,20 / 9,37% | **3,558 / 6,471 / 10,204 / 9,368%** | ver §3.3 |
| Armadilha: inadimplencia jun/26 sem filtro PIT de cancelamento | 18,7% | **18,70%** | numerador sem `data_cancelamento` |
| Aging em REF (excl. cancelados e baixados) | 4,47 / 0,76 / 0,44 / 0,40 / 0,77 / 0,82 mi | **4,4707 / 0,7612 / 0,4373 / 0,4026 / 0,7699 / 0,8205 mi** | ver §3.5 |
| Faturamento x meta 2024 / 2025 / 2026(8m) | −2,7 / +6,8 / +2,9% | **−2,66 / +6,78 / +2,92%** | BRL: realizado do periodo ÷ soma das metas **mensais vigentes do mesmo periodo** |
| Recebimento x meta 2024 / 2025 / 2026(8m) | −4,7 / −2,9 / +3,6% | **−4,67 / −2,94 / +3,64%** | `sum(valor_pago)` por `month(data_pagamento)`, **juros/multa incluidos** |
| Margem x meta 2024 / 2025 | −0,34 / −0,98 p.p. | **−0,34 / −0,98 p.p.** | realizado anual − meta **anual** |
| Inadimplencia x meta 2024 / 2025 | +0,56 / +7,20 p.p. | **+0,56 / +7,20 p.p.** | valor de dezembro − meta anual (Fim de Periodo) |
| Coerencia do orcamento | "zero divergencias" | **confirmado** | 12 mensais = 4 trimestrais = anual (BRL); margem anual recalculada de RL e Custo = 35,00 / 35,50 / 33,00% exato |

### 2.2 NAO bateram — divergencia de definicao

| # | Publicado | Apurado | Diagnostico e definicao adotada |
|---|---|---|---|
| D1 | **Cancelamentos 4,0 / 6,0 / 2,0%** (2024/25/26) | **3,53 / 6,23 / 1,97%** por competencia; **1,22 / 5,45 / 5,88%** por ano de cancelamento | Nenhuma das duas reproduz 4,0% em 2024. Os valores absolutos conferem (R$ 1,051 / 2,182 / 0,486 mi cancelados por competencia). Sao **parametros do gerador**, nao uma metrica reconstituivel. **Adotar: por competencia** (`sum(valor_bruto) filter (data_cancelamento is not null) / sum(valor_bruto)`), e nao publicar 4,0/6,0/2,0 no app. |
| D2 | **Inadimplencia 2026 x meta: +2,02 p.p. (ago)** | **+1,22 p.p.** | Reproduz-se apenas comparando o realizado de **ago/2026 (10,02%)** com a meta **anual** (8,00%, que e a meta de **dez**/2026). A meta de ago/2026 e **8,80%**. Comparar mes contra meta de outro mes e erro de periodo. **Adotar: mes-a-mes contra a meta do mesmo `ano_mes` → +1,22 p.p.**; a comparacao anual so vale em dezembro. |
| D3 | **Margem 2026 x meta: −0,61 p.p.** | **−0,61 p.p.** contra a meta anual (33,00%); **+1,70 p.p.** contra a meta ponderada dos 8 meses (**30,69%**) | O sinal **inverte**. A `Revisao 2026` travou jan-mar no realizado, e jan/fev tem margem baixissima por sazonalidade de IPVA (13,38% e 10,76%), o que derruba a meta ponderada do periodo parcial. **Adotar: media ponderada por Receita Liquida meta dos meses do periodo selecionado → +1,70 p.p. em 2026(8m).** Nunca comparar 8 meses com a meta anual. |

### 2.3 Duas inconsistencias internas do dataset (registrar, nao corrigir)

- **Baixados entram na inadimplencia mas nao no aging.** O numerador de §3.3 nao filtra `data_baixa` (R$ 3,520 mi em REF);
  o aging de §3.5 filtra `data_baixa is null` (R$ 3,192 mi vencido). Diferenca: **R$ 328 mil**. E assim que os numeros
  publicados foram gerados — manter, e rotular no app: *"aging exclui titulos baixados; inadimplencia nao."*
- **4 titulos (R$ 182 mil) tem `data_baixa` posterior a REF** (2026-09-15 a 2026-10-19). Nao use `data_baixa is null` como
  proxy de "vivo em REF"; se quiser point-in-time real, use `data_baixa is null or data_baixa > :ref` — mas isso **nao**
  reproduz o aging publicado. Nenhum `data_cancelamento` e futuro. 107 titulos (R$ 3,075 mi) tem `data_emissao` em
  2026-09-01 — e a regra de emissao no 1o dia util apos a competencia, esperado.

---

## 3. Definicoes canonicas (contrato de calculo)

Notacao: `T` = `titulos_receber`, `C` = `custos`, `:ref` = data de referencia, `:ini`/`:fim` = janela de competencia.

### 3.1 Faturamento Bruto
```sql
sum(T.valor_bruto) where T.competencia between :ini and :fim
```
Sem filtro de cancelamento (assim foi publicado). Variante **Faturamento Valido** (para analise de receita real):
`+ and (T.data_cancelamento is null or T.data_cancelamento > :ref)`. Diferenca no 12m ago/26: 36,384 → **35,120 mi**.

### 3.2 Receita Liquida e Margem Operacional
```sql
receita_liquida = sum(T.valor_liquido)                       -- INCLUINDO cancelados
custo_operacional = sum(C.valor)                             -- INCLUINDO ocioso (id_contrato is null)
margem_pct = 100 * (receita_liquida - custo_operacional) / receita_liquida
```
Variantes apuradas (2024 / 2025 / 2026-8m), para o app **nunca** confundir:

| Variante | 2024 | 2025 | 2026(8m) | Uso |
|---|---|---|---|---|
| **Margem Operacional (publicada)** | **34,66%** | **34,52%** | **32,39%** | KPI oficial, unico com meta |
| Excluindo titulos cancelados do denominador | 32,26% | 30,17% | 31,02% | nunca exibir sem rotulo |
| Excluindo custo ocioso (= "margem de contratos") | 35,72% | 35,60% | 34,28% | unica valida com filtro de segmento/cliente |
| Excluindo custo `Nao Caixa` (proxy EBITDA) | 56,90% | 56,79% | 53,90% | pagina de frota, rotulada |

### 3.3 Inadimplencia > 30 dias (point-in-time) — **a metrica central**
```sql
numerador = sum(T.valor_bruto)
  where T.data_vencimento <= :ref - 30
    and (T.data_pagamento     is null or T.data_pagamento     > :ref)
    and (T.data_cancelamento  is null or T.data_cancelamento  > :ref)
denominador = sum(T.valor_bruto)
  where T.competencia >= date_trunc('month', :ref) - interval '11 months'
    and T.competencia <= date_trunc('month', :ref)
    and (T.data_cancelamento is null or T.data_cancelamento > :ref)
inadimplencia_pct = 100 * numerador / denominador
```
Sem filtro de `data_baixa` nos dois lados. Serie apurada (realizado x meta vigente):

| Mes | 2024 | meta | 2025 | meta | 2026 | meta |
|---|---|---|---|---|---|---|
| Jan | 0,00* | 3,50 | 5,03 | 3,50 | 10,75 | 10,75 |
| Fev | 0,00* | 3,40 | 4,56 | 3,40 | 8,43 | 8,43 |
| Mar | 0,16* | 3,30 | 4,31 | 3,40 | 9,06 | 9,06 |
| Abr | 4,02* | 3,20 | 6,39 | 3,30 | 9,85 | 9,60 |
| Mai | 8,74* | 3,10 | 8,07 | 3,20 | 10,43 | 9,40 |
| Jun | 5,98* | 3,00 | **6,47** | 3,20 | **9,37** | 9,20 |
| Jul | 5,60* | 3,00 | 5,93 | 3,10 | 9,60 | 9,00 |
| Ago | 4,39* | 3,00 | 6,05 | 3,10 | **10,02** | 8,80 |
| Set | 4,08* | 3,00 | 6,92 | 3,00 | — | 8,60 |
| Out | 4,53* | 3,00 | **9,79** | 3,00 | — | 8,40 |
| Nov | 4,41* | 3,00 | **10,29** | 3,00 | — | 8,20 |
| Dez | **3,56** | 3,00 | **10,20** | 3,00 | — | 8,00 |

`*` = janela de 12 meses incompleta (efeito base). **Nao exibir jan/2024 a dez/2024 como serie comparavel**;
liberar a serie a partir de **jan/2025**. Jan-mar/2026 tem desvio zero **por construcao** (reforecast travado).

### 3.4 Recebimento (Caixa)
```sql
sum(T.valor_pago) where T.data_pagamento between :ini and :fim   -- juros e multa INCLUIDOS
```
Realizado: 24,461 (2024) · 30,601 (2025) · 22,804 mi (2026-8m). Sem juros: 24,242 / 30,252 / 22,469 mi
(a versao **com** juros e a que reproduz o desvio publicado). **Eficiencia de cobranca 12m** (set/25-ago/26) =
32,958 / 35,120 = **93,8%** — acima do piso de 93% da `Revisao 2026`, abaixo dos 97% do orcamento original.

### 3.5 Aging da carteira (foto em `:ref`)
```sql
where T.data_pagamento is null and T.data_cancelamento is null and T.data_baixa is null
faixa = a vencer | 1-30 | 31-60 | 61-90 | 91-180 | 180+   -- por (:ref - T.data_vencimento)
```
Em REF: a vencer **4,471** · 1-30d **0,761** · 31-60d **0,437** · 61-90d **0,403** · 91-180d **0,770** · 180+ **0,821** mi.
Total vencido **3,192 mi**; carteira total em aberto **7,663 mi**; **% vencido da carteira = 41,7%**.

### 3.6 Realizado x Meta — regra unica
```sql
-- BRL (Faturamento, Receita Liquida, Custo Operacional, Recebimento): soma das metas MENSAIS vigentes do periodo
where eh_versao_vigente and granularidade='Mensal' and ano_mes between :ini_ym and :fim_ym
-- Margem Operacional (%): media ponderada pela META de Receita Liquida dos mesmos meses
sum(meta_RL - meta_Custo) / sum(meta_RL)
-- Inadimplencia > 30d (%): meta do ULTIMO mes do periodo (tipo_agregacao = 'Fim de Periodo')
```
`eh_versao_vigente = true` **sempre**. Sem ele, 2026 duplica (Original 37,80 mi + Revisao 35,82 mi = 73,62 mi).
Metas de **Custo, Margem e Inadimplencia so existem em `nivel_analise='Empresa'`** — qualquer filtro de segmento
deve **apagar** a comparacao com meta nessas tres.

### 3.7 Custo de Ociosidade
```sql
sum(C.valor) where C.id_contrato is null    -- equivalente a C.veiculo_ocioso = true (conferido: identicos)
taxa_ociosidade = count(distinct id_veiculo) filter (id_contrato is null) / count(distinct id_veiculo)  -- por mes
```
**Nao tem cliente, contrato nem segmento.** Nunca filtrar por essas dimensoes.

### 3.8 Margem por Contrato — **so com periodo casado**
```sql
-- receita e custo do MESMO conjunto de competencias em que o contrato faturou
```
Sem isso o resultado e lixo: `CTR0023` (Construtora Jatapu 044) aparece com **−671%** de margem porque encerrou em
2024-01-03 — recebeu 3 dias de receita (R$ 20 mil liquidos) contra o **custo cheio de janeiro de 10 veiculos**
(R$ 154 mil). Corrigido esse artefato, ha **5 contratos com margem acumulada negativa** (confirmando a narrativa),
mas o prejuizo real e de **R$ 15 mil**, nao R$ 149 mil.

---

## 4. As historias, com nome e valor

### 4.1 O cliente Grande que para de pagar: **Servicos Manicore S.A. 001** (`CLI0001`)
Grande · Agronegocio · rating **C** · limite R$ 1,259 mi · contrato ativo `CTR0071` (4 veiculos, R$ 50 mil/mes).

| Competencia | Vencimento | Valor | Pago em | Atraso |
|---|---|---|---|---|
| jul/25 | 2025-09-01 | 51,6 mil | 2025-08-29 | **0 d** |
| ago/25 | 2025-10-01 | 53,1 mil | 2025-12-23 | **83 d** |
| set/25 | 2025-10-31 | 53,2 mil | 2026-02-27 | **119 d** |
| nov/25 | 2025-12-31 | 52,8 mil | 2026-03-11 | 70 d |
| dez/25 | 2026-02-02 | 52,8 mil | 2026-04-24 | 81 d |
| **jan/26** | 2026-03-04 | **52,8 mil** | — | **nunca pago** |
| **mar/26** | 2026-05-01 | **51,9 mil** | — | **nunca pago** |
| **jun/26** | 2026-07-31 | **54,9 mil** | — | **nunca pago** |

Vencido > 30d, mes a mes: **zero** ate set/2025 → 53,1 mil (out/25) → 113,8 (nov/25) → 111,3 (jan/26) → 157,5 (mai/26)
→ **159,5 mil (ago/26)**. Taxa de titulos "ruins" (nao pagos ou pagos com >30d de atraso, controlada por maturidade):
**18,2% antes de set/25 → 75,0% depois**. Impacto acumulado vs. o proprio historico: **R$ 245 mil**.
**Peso:** R$ 655 mil de faturamento nos ultimos 12 meses = **1,8% da receita**, mas **4,5% do vencido** e
**24,4% do proprio faturamento 12m parado**. Continua faturando — a decisao pendente e suspender ou renegociar.

### 4.2 Construcao Civil se deteriora no 2S/2025
Inadimplencia do segmento (mesma formula de §3.3, numerador e denominador do segmento):

| dez/24 | jun/25 | **dez/25** | jun/26 | ago/26 |
|---|---|---|---|---|
| 5,32% | 11,85% | **20,24%** | 15,65% | 18,07% |

No salto de set→nov/2025 (empresa: 6,92% → 10,29%), a Construcao Civil sozinha adicionou **R$ 317 mil** de novo
vencido (de 567 para 884 mil), atras apenas de Logistica e Transporte (**R$ 430 mil**, mas com 2,8x mais receita).
**Sobrerrepresentacao: 14,2% do faturamento 12m, 25,6% do vencido (1,80x).** Nomes: `CLI0034` Logistica Maues S.A. 034
(Grande, D — 40,0% do proprio faturamento vencido), `CLI0019` Transportes Uatuma 019 (37,4%),
`CLI0015` Transportes Manicore 015 (Grande, C — 32,2%), `CLI0030` Servicos Ponta Negra 030 (20,2%).
A margem do segmento tambem e a 3a pior: **32,5%** (12m) contra 39,3% de Energia e Saneamento.

### 4.3 Contratos com margem negativa — e o falso positivo
Periodo casado, todo o historico:

| Contrato | Cliente | Tipo | RL | Custo | Margem | % corretiva | Causa |
|---|---|---|---|---|---|---|---|
| `CTR0023` | Construtora Jatapu 044 | c/ Motorista | 20 mil | 154 mil | **−671%** | 1,0% | **artefato de borda** (encerrou 2024-01-03) |
| `CTR0151` | Transportes Silves 020 | Spot | 7 mil | 10 mil | −46,9% | **44,4%** | corretiva |
| `CTR0119` | Mineracao Novo Airao 036 | Spot | 22 mil | 31 mil | −37,9% | **26,3%** | corretiva |
| `CTR0041` | Mineracao Maues 054 | Spot | 21 mil | 23 mil | −9,9% | **22,6%** | corretiva |
| `CTR0121` | Transportes Madeira 047 | Spot | 12 mil | 13 mil | −9,0% | 8,2% | contrato curto |

Prejuizo real (ex-`CTR0023`): **R$ 15 mil**. Os proximos da fila, materiais e **ativos**: `CTR0110` (Construtora
Manicore 012, 7,3% sobre R$ 376 mil), `CTR0057` (Transportes Manicore 015, 11,5% sobre R$ 1,125 mi),
`CTR0113` (14,5%), `CTR0127` (15,3%), `CTR0116` (16,4%). **Locacao Spot e Terceirizacao de Frota concentram o
problema**: margem 12m por tipo — Terceirizacao **30,0%** · c/ Motorista 37,0% · Mensal Frota 38,8% · Spot 41,3%
(a media do Spot esconde a variancia: e onde estao 4 dos 5 negativos).

**Causa raiz — idade da frota** (custo 12m, set/25-ago/26):

| Idade | Veiculos | Corretiva 12m | Por veiculo | % do custo |
|---|---|---|---|---|
| 0-2 anos | 65 | R$ 577 mil | **R$ 8,9 mil** | 9,2% |
| 3-4 anos | 68 | R$ 883 mil | R$ 13,0 mil | 13,3% |
| 5-6 anos | 66 | R$ 1.011 mil | R$ 15,3 mil | 17,0% |
| **7+ anos** | **45** | **R$ 1.043 mil** | **R$ 23,2 mil** | **29,5%** |

Trocar os 45 veiculos de 7+ anos por frota de 0-2 anos economizaria **~R$ 644 mil/ano** em corretiva.

### 4.4 Quanto custa a ociosidade
Custo de veiculo sem contrato: **R$ 297 mil (2024)** · **R$ 357 mil (2025)** · **R$ 434 mil (8m de 2026)** — anualizado,
**+82% sobre 2025**. Componente caixa (excl. Depreciacao/Nao Caixa): R$ 313 mil em 2026(8m). Nos 12 meses moveis:
**R$ 612 mil**, **2,7% do custo operacional total (R$ 22,391 mi)** e **1,8 p.p. de margem** (36,1% → 34,3%).
Picos de frota parada: **nov/25 15 veiculos (6,7%)** · **fev/26 15 (6,4%)** · **jul/26 11 (4,6%)** · **ago/26 15 (6,3%)**.
Por categoria (12m): Caminhonete 4x4 R$ 147 mil · Cavalo Mecanico R$ 108 mil · Caminhao Munck R$ 107 mil.
**A ociosidade esta subindo justamente no fim da serie** — e o unico indicador operacional em piora clara.

### 4.5 Concentracao — curva ABC (12m moveis, set/25-ago/26, liquido de cancelados)

| Classe | Clientes | Faturamento 12m | Share |
|---|---|---|---|
| **A** (ate 50% acum.) | **12** | R$ 17,235 mi | **49,1%** |
| B (50-80%) | 14 | R$ 10,656 mi | 30,3% |
| C (80-100%) | 27 | R$ 7,229 mi | 20,6% |

53 clientes faturaram nos ultimos 12 meses (de 58 cadastrados). Top 5 = 23,1%; maior cliente
(`CLI0058` Energia Novo Airao 058, PME, B) = **5,97%** — nao ha dependencia critica de um unico nome na receita.
O risco esta do outro lado: **os 5 maiores devedores concentram 33,2% do vencido e os 10 maiores, 56,8%**
(36 clientes com vencido > 30d). **Ratings C+D = 70,8% do vencido** com 22 dos 53 clientes.
**Exposicao acima do limite de credito** (em aberto ÷ `limite_credito`, REF): **13 clientes** — Agropecuaria Trombetas 028
**283%** · Mineracao Anori 051 237% · Energia Novo Airao 058 229% · Servicos Autazes 023 206% ·
Servicos Itapiranga 053 196% · Agropecuaria Negro 024 164%.

### 4.6 Onde o realizado mais desvia da meta vigente

**Nivel empresa** — o unico confiavel:

| Ano | Faturamento | Recebimento | Margem | Inadimplencia |
|---|---|---|---|---|
| 2024 | −2,66% | −4,67% | −0,34 p.p. | +0,56 p.p. (dez) |
| 2025 | **+6,78%** | −2,94% | −0,98 p.p. | **+7,20 p.p. (dez)** |
| 2026 (8m) | +2,92% | +3,64% | **+1,70 p.p.**¹ | +1,22 p.p. (ago)² |

¹ contra a meta ponderada dos 8 meses (30,69%); contra a meta anual (33,0%) daria −0,61 p.p. — ver D3.
² contra a meta de ago/2026 (8,80%); contra a meta anual (8,00%) daria +2,02 p.p. — ver D2.

**Nivel segmento** — o orcamento erra o mix, nao o total. Faturamento realizado x meta:

| Segmento | 2025 | 2026 (8m) |
|---|---|---|
| Logistica e Transporte | **+83,9%** | **+24,9%** |
| Industria | +29,8% | −3,2% |
| Mineracao | +13,7% | −3,0% |
| Energia e Saneamento | −57,1% | +20,8% |
| Construcao Civil | −10,4% | +16,7% |
| Agronegocio | −10,1% | −30,0% |
| Varejo e Distribuicao | −11,5% | **−42,1%** |
| Servicos Publicos | **−67,2%** | −32,5% |

**Consequencia de produto:** o desvio por segmento e dominado por erro de composicao do orcamento (a participacao dos
segmentos foi herdada do ano anterior e achatada), nao por performance comercial. O app deve exibir a variacao por
segmento com **aviso explicito** e nunca usa-la como sinal de alerta automatico. O sinal confiavel e o total da empresa.

---

## 5. KPIs

### 5.1 Primarios (topo de todas as paginas, no maximo 6)

Criterio de escolha: cada um responde a uma pergunta que muda uma decisao **nesta semana** — vender mais, cortar custo,
liberar caixa, cortar credito. Nao entraram metricas que so descrevem (ex.: Receita Liquida, que e faturamento x aliquota
e nao tem alavanca propria; virou secundaria como denominador da margem).

| # | KPI | Definicao (1 frase) | Formula | Unid./formato | Granularidade | Direcao | Armadilha | Meta em `metas` |
|---|---|---|---|---|---|---|---|---|
| **P1** | **Faturamento Bruto** | Valor emitido por competencia, antes de impostos. | §3.1 | BRL · `R$ 1.234.567` | mes · trimestre · ano · segmento · cliente · contrato · tipo de receita | ↑ maior melhor | Ano de 2026 e parcial (8m): comparacao anual sem ajuste de periodo mente | `Faturamento`, Soma, Empresa **e Segmento** |
| **P2** | **Margem Operacional** | Quanto sobra da receita liquida depois de todo o custo, inclusive de veiculo parado. | §3.2 | % · `34,7%`, desvio em `p.p.` | mes · trimestre · ano · **so Empresa quando ha custo ocioso** | ↑ maior melhor | Denominador **inclui** cancelados; com filtro de segmento o custo ocioso some e a margem sobe ~1,8 p.p. artificialmente | `Margem Operacional`, **Media Ponderada por Receita Liquida**, so Empresa |
| **P3** | **Inadimplencia > 30d (point-in-time)** | Do faturado nos ultimos 12 meses, quanto esta vencido ha mais de 30 dias e ainda vivo na data de referencia. | §3.3 | % · `10,02%`, desvio em `p.p.` | mes (fim de mes) · segmento · porte · rating · cliente | ↓ menor melhor | Sem filtro PIT de cancelamento vai de 9,37% a **18,70%**; janela de 12m so estabiliza em **jan/2025** | `Inadimplencia > 30d`, **Fim de Periodo**, so Empresa |
| **P4** | **Recebimento (Caixa)** | Quanto entrou no caixa no periodo, por data de pagamento. | §3.4 | BRL | mes · trimestre · ano · segmento · cliente | ↑ maior melhor | E por `data_pagamento`, **nao** por competencia — nao soma com faturamento do mesmo mes; inclui juros/multa | `Recebimento (Caixa)`, Soma, Empresa **e Segmento** |
| **P5** | **Custo Operacional** | Custo total da operacao no periodo, com ocioso e depreciacao. | §3.2 | BRL | mes · trimestre · ano · categoria · tipo · veiculo · contrato | ↓ menor melhor | Sazonalidade brutal de IPVA em jan-fev (R$ 707+711 mil em 2026): serie mensal precisa de media movel ou comparativo YoY | `Custo Operacional`, Soma, **so Empresa** |
| **P6** | **Carteira Vencida** | Saldo em aberto ja vencido na data de referencia, em reais. | §3.5 (faixas > 0 dias) | BRL + % da carteira · `R$ 3,19 mi (41,7%)` | foto em `:ref` · segmento · rating · cliente · faixa de aging | ↓ menor melhor | E **foto**, nao periodo: o filtro de competencia **nao** se aplica; exclui baixados (a inadimplencia nao) | **sem meta** — exibir sem gauge |

### 5.2 Secundarios, por pagina

| KPI | Definicao | Formula / valor apurado | Unid. | Direcao | Armadilha |
|---|---|---|---|---|---|
| Receita Liquida | Faturamento menos impostos (3,65% ou 8,65%). | `sum(valor_liquido)` incl. cancelados · 34,074 mi (12m) | BRL | ↑ | Denominador oficial da margem; a versao ex-cancelados difere em 3,7% |
| Cancelamentos % | Parcela do faturado que foi cancelada. | por competencia · 3,53 / 6,23 / 1,97% | % | ↓ | Nao reproduz 4,0/6,0/2,0 do briefing (D1) |
| Ticket medio mensal por contrato ativo | Faturamento ÷ contratos com faturamento no mes. | — | BRL | ↑ | Contratos Spot distorcem (duracao < 1 mes) |
| Mix de receita | Share por `tipo_receita`. | Locacao **96,2%** · Avaria 1,2% · KM Exc. 0,9% · Serv. Adic. 0,7% · Multa Resc. 0,5% · Multa Transito 0,4% | % | — | Receita acessoria e residual: nao construir pagina para ela |
| Curva ABC de clientes | Classificacao por faturamento 12m acumulado (A ate 50%, B ate 80%, C resto). | A: 12 cli / 49,1% · B: 14 / 30,3% · C: 27 / 20,6% | # e % | — | Janela de 12m: antes de jan/2025 nao existe |
| Aging por faixa | §3.5 | 4,471 / 0,761 / 0,437 / 0,403 / 0,770 / 0,821 mi | BRL | ↓ nas faixas altas | Exclui baixados e cancelados |
| Taxa de recuperacao de vencidos | Dos titulos que passaram de 30d de atraso, quanto foi pago. | R$ 9,822 mi de R$ 13,342 mi = **73,6%**, em media **92 dias** de atraso | % e dias | ↑ | Titulos recentes ainda nao tiveram tempo: filtrar `data_vencimento <= :ref - 90` |
| Atraso medio ponderado | Media de `dias_atraso_pagamento` ponderada por `valor_bruto`, dos pagos no periodo. | **20,9 dias** (12m); prazo emissao→pagamento **43,0 dias** | dias | ↓ | So ve quem pagou — melhora artificialmente quando os piores param de pagar |
| Eficiencia de cobranca | Recebimento 12m ÷ Faturamento valido 12m. | 32,958 / 35,120 = **93,8%** | % | ↑ | Descasamento temporal: caixa de m reflete faturamento de m−1 a m−3 |
| Juros e multa recuperados | `sum(valor_juros_multa)` | **R$ 902,7 mil** no historico | BRL | ↑ | Receita nao recorrente; nao entra em `titulos_receber.valor_bruto` |
| Baixas por motivo | `sum(valor_baixa)` por `motivo_baixa`. | Perda Cobravel **R$ 664 mil** (21) · Glosa 207 (5) · Baixa Caixa 196 (7) · Cortesia 22 (2) | BRL | ↓ | 4 titulos (R$ 182 mil) tem `data_baixa` **futura** a REF |
| Cancelamentos por motivo | `sum(valor_bruto)` por `motivo_cancelamento`. | Renegociacao **R$ 1,280 mi** · Fat. Indevido 1,177 · Erro de Emissao 597 · Acordo 347 · Troca de Veiculo 319 | BRL | ↓ | "Faturamento Indevido" + "Erro de Emissao" = **R$ 1,774 mi de falha de processo**, nao de comercial |
| Uso do limite de credito | Em aberto ÷ `limite_credito` por cliente. | **13 clientes > 100%**; max **283%** | % | ↓ | `limite_credito` e nullable |
| Exposicao por rating | Vencido > 30d por `rating_credito`. | A 0,4% · B 28,8% · C **47,5%** · D **23,3%** | % | ↓ | Rating e atributo estatico do cadastro, sem historico |
| Margem por contrato | §3.8, **periodo casado**. | 5 negativos, prejuizo real R$ 15 mil (ex-artefato) | % e BRL | ↑ | Sem casar periodo, `CTR0023` mostra −671% |
| Margem por tipo de contrato | RL ÷ custo por `tipo_contrato` (12m). | Terceirizacao **30,0%** · c/ Motorista 37,0% · Mensal Frota 38,8% · Spot 41,3% | % | ↑ | Exclui ocioso por construcao — rotular "margem de contratos" |
| Margem por segmento | idem, por segmento do cliente (12m). | Varejo **24,2%** · Serv. Publicos 29,2% · Constr. Civil 32,5% · Industria 37,5% · Logistica 38,0% · Mineracao 38,1% · Agronegocio 38,3% · Energia 39,3% | % | ↑ | Idem: nao soma com a margem consolidada (falta R$ 612 mil de ocioso) |
| Custo de ociosidade | §3.7 | R$ 612 mil (12m) = **2,7% do custo**, **1,8 p.p. de margem** | BRL | ↓ | **Sem segmento, cliente ou contrato** |
| Taxa de ociosidade da frota | Veiculos sem contrato ÷ frota do mes. | ago/26 **15 de 239 = 6,3%** | % | ↓ | Grao mensal: um veiculo alocado dia 20 conta o mes inteiro como alocado |
| Corretiva por veiculo-ano | Corretiva 12m ÷ veiculos da faixa de idade. | 0-2a R$ 8,9 mil → 7+a **R$ 23,2 mil** | BRL | ↓ | Idade = `2026 − ano_modelo`; `ano_modelo` e nullable |
| Frota e valor | Contagem e valor de aquisicao. | 238 ativos (R$ 80,27 mi, idade media **4,2 anos**) · 7 vendidos (R$ 2,42 mi, 6,6 anos) | # e BRL | — | 1 veiculo nunca foi alocado |
| Churn contratual | Contratos rescindidos e Multa Rescisoria. | 10 rescindidos (2 em 2023, 3 em 2024, **4 em 2025**, 1 em 2026); multa R$ 550/278/99 mil | # e BRL | ↓ | Multa Rescisoria e receita nao recorrente: inflar tendencia se somada a Locacao |
| MRR contratado | `sum(valor_mensal_contratado)` dos contratos `Ativo`. | **R$ 2,773 mi/mes** em 78 contratos ativos | BRL | ↑ | Valor de assinatura do contrato, sem reajuste aplicado — nao bate com o faturado |

---

## 6. Estrutura do app — 5 paginas

| # | Pagina | Pergunta de negocio | Publico | KPIs | Decisao que habilita |
|---|---|---|---|---|---|
| **1** | **Visao Executiva** | "Estamos entregando o plano? Se nao, onde exatamente quebrou?" | **CFO** | P1-P6 com realizado, meta vigente e desvio; serie mensal de faturamento e margem; ponte realizado→meta; toggle `Orcamento Original` x `Revisao 2026` (2026) | Levar ao board a leitura correta: receita e caixa acima do plano, credito fora de controle. Decidir se o reforecast de 2026 precisa de nova revisao. |
| **2** | **Receita e Carteira** | "De onde vem a receita, quanto ela esta concentrada e onde o mix desviou do orcamento?" | **Controller** / CFO | P1, P4, Receita Liquida, Cancelamentos %, mix por `tipo_receita`, curva ABC, faturamento x meta **por segmento** (com aviso de mix), YoY 2024→2025, MRR contratado, churn | Priorizar carteira comercial; atacar os R$ 1,774 mi de cancelamento por erro de emissao/faturamento indevido; corrigir a premissa de mix do proximo orcamento. |
| **3** | **Credito e Cobranca** | "Quem nao esta pagando, ha quanto tempo, quanto pesa e o que ainda da para recuperar?" | **Gerente de credito e cobranca** | P3, P6, aging por faixa, inadimplencia PIT por segmento/rating/porte, taxa de recuperacao (73,6% / 92 dias), atraso medio ponderado (20,9 d), eficiencia de cobranca (93,8%), uso do limite de credito, ranking de devedores, baixas por motivo | Suspender faturamento de cliente acima do limite; escalar cobranca dos 10 maiores devedores (56,8% do vencido); pedir garantia adicional em Construcao Civil e ratings C/D. |
| **4** | **Margem e Contratos** | "Quais contratos destroem valor e por que?" | **Controller** / gerente de operacao | P2, P5, margem por contrato (periodo casado), por tipo de contrato, por segmento, contratos negativos e a lista dos <20%, % de corretiva por contrato, RL vs custo | Renegociar ou encerrar contrato deficitario; repactuar preco em Terceirizacao de Frota (30,0%) e Varejo (24,2%). |
| **5** | **Frota e Ociosidade** | "Quanto custa a frota parada e a frota velha?" | **Gerente de operacao e frota** | Custo de ociosidade (R$ 612 mil/12m), taxa de ociosidade mensal, custo por categoria de custo e tipo (Fixo/Variavel/Nao Caixa), corretiva por faixa de idade, custo e ociosidade por categoria de veiculo, idade media, margem ex-Nao Caixa | Aprovar renovacao dos 45 veiculos de 7+ anos (~R$ 644 mil/ano de corretiva evitavel); realocar ou vender os 15 veiculos parados em ago/26. |

Ordem de navegacao = ordem da tabela. Paginas 3, 4 e 5 sao as "profundas"; 1 e 2 sao de leitura rapida.

---

## 7. Filtros globais

| Filtro | Valores | Padrao inicial | Observacao |
|---|---|---|---|
| **Periodo de competencia** | mes inicial / mes final entre `2024-01` e `2026-08` | **`2025-09` a `2026-08`** (12 meses moveis fechados) | Presets: *Ultimos 12m* · *2026 YTD (8m)* · *2025* · *2024* · *Tudo*. Em presets de ano parcial, o app **deve** comparar com a meta dos mesmos meses. |
| **Data de referencia** | qualquer fim de mes entre `2024-12-31` e `2026-08-31` | **`2026-08-31`** | Dirige P3 e P6. Independente do periodo de competencia. Bloquear anterior a `2024-12-31`. |
| **Segmento** | 8 valores | todos | |
| **Porte** | Grande · Medio · PME | todos | |
| **Rating de credito** | A · B · C · D · (sem rating) | todos | |
| **Tipo de contrato** | 4 valores | todos | |
| **Cliente** | busca multi-selecao (58) | vazio | |
| **Versao de orcamento** | vigente (padrao) · comparar Original x Revisao | **vigente** | Visivel **so na pagina 1** e so quando o periodo toca 2026. Fora dela, `eh_versao_vigente = true` fixo. |

### 7.1 O que os filtros NAO podem filtrar — regras duras

| Metrica | Filtro que **nao** se aplica | Comportamento exigido |
|---|---|---|
| **Inadimplencia > 30d (P3)** | Periodo de competencia | O denominador e **sempre** a janela fixa de 12 meses que termina na data de referencia. O periodo so muda o eixo x da serie. Exibir a janela usada no rodape do card. |
| **Inadimplencia > 30d (P3)** | Datas anteriores a `2025-01-31` | Janela de 12m incompleta (efeito base): jan/24 = 0,00%, mai/24 = 8,74% sao artefatos. Serie **cinza tracejada** e sem alerta antes de jan/2025. |
| **Inadimplencia, Custo Operacional, Margem — comparacao com meta** | Segmento, porte, rating, cliente, tipo de contrato | As metas dessas 3 metricas so existem em `nivel_analise='Empresa'`. Qualquer filtro dimensional deve **remover o gauge de meta** e mostrar "meta indisponivel neste recorte". |
| **Custo de Ociosidade e Taxa de Ociosidade** | Segmento, cliente, contrato, rating, porte, tipo de contrato | `custos.id_contrato is null` — nao ha a quem atribuir. Com qualquer desses filtros ativo, o card fica **desabilitado** com nota "custo de veiculo ocioso nao possui atribuicao por cliente". |
| **Custo Operacional e Margem Operacional (P2/P5)** | Segmento, cliente, contrato | Filtrar por essas dimensoes **exclui silenciosamente R$ 612 mil (12m)** de custo ocioso e infla a margem de 34,3% para 36,1%. Com filtro ativo, renomear o KPI para **"Margem de Contratos"** e marcar com badge. |
| **Carteira Vencida e Aging (P6)** | Periodo de competencia | E foto na data de referencia, nao acumulado de periodo. O filtro de competencia fica visivelmente inativo no card. |
| **Recebimento (Caixa) (P4)** | — | Filtra por `data_pagamento`, nao por competencia. Nunca somar com Faturamento do mesmo mes (defasagem de 1 a 3 meses). Rotular o eixo como "mes de caixa". |
| **Faturamento por segmento x meta** | — | Exibir sempre com aviso: *"a meta por segmento herda o mix do ano anterior; desvios de ate ±80% refletem composicao do orcamento, nao performance"* (ex.: Logistica +83,9% em 2025). |
| **Margem por contrato (P4)** | — | Sempre com periodo casado (§3.8). Excluir da lista contratos com 1 mes de receita e `data_fim_efetiva` no primeiro dia util do mes; sinalizar como "periodo parcial". |

---

## 8. Alertas e limiares

Regras objetivas, avaliadas na data de referencia. Cada uma vem com o resultado apurado em `2026-08-31`.

### 8.1 Empresa (pagina 1)

| ID | Regra | Ambar | Vermelho | Situacao em REF |
|---|---|---|---|---|
| **A1** | Inadimplencia PIT do mes **vs. meta do mesmo `ano_mes`** | ≥ +1,0 p.p. | ≥ +2,0 p.p. | **10,02% vs 8,80% = +1,22 p.p. → AMBAR** |
| **A2** | Inadimplencia PIT sobe ≥ 1,5 p.p. em 3 meses | — | atingido | jun→ago/26: 9,37 → 10,02 = +0,65 p.p. → ok |
| **A3** | Faturamento do mes vs. meta mensal vigente | < 95% | < 90% | 2026 (8m): 102,9% → ok |
| **A4** | Eficiencia de cobranca 12m (§3.4) | < 95% | < 93% | **93,8% → AMBAR** |
| **A5** | Margem 12m vs. meta ponderada do periodo | ≤ −1,0 p.p. | ≤ −2,0 p.p. | 2026(8m) +1,70 p.p. → ok |
| **A6** | Custo mensal > meta mensal vigente | > 105% | > 110% | acompanhar jan-fev (pico de IPVA) |

### 8.2 Credito e cobranca (pagina 3)

| ID | Regra | Ambar | Vermelho | Quem dispara em REF |
|---|---|---|---|---|
| **A7** | Vencido > 30d do cliente ÷ faturamento 12m do cliente | ≥ 10% | ≥ 20% | **8 vermelhos + 11 ambar**. Vermelhos: Servicos Coari 010 (46,1%) · Logistica Maues 034 (40,0%) · Transportes Uatuma 019 (37,4%) · Engenharia Codajas 048 (36,4%) · Transportes Manicore 015 (32,2%) · Mineracao Anori 051 (24,9%) · **Servicos Manicore 001 (24,4%)** · Servicos Ponta Negra 030 (20,2%) |
| **A8** | Exposicao em aberto ÷ `limite_credito` | ≥ 80% | ≥ 100% → **bloquear novo faturamento** | **13 vermelhos + 1 ambar**, lidera Agropecuaria Trombetas 028 (283%) |
| **A9** | Inadimplencia do segmento ÷ inadimplencia da empresa | ≥ 1,5x | ≥ 2,0x | **Servicos Publicos 18,45% (1,84x)** e **Construcao Civil 18,07% (1,80x)** → ambar |
| **A10** | Cliente com titulo vencido ha > 180 dias | qualquer | ≥ R$ 100 mil | faixa 180+ = R$ 821 mil em 28 titulos |
| **A11** | Cliente Grande/A com **vencido > 30d saindo de zero** (2 meses consecutivos) | — | atingido | **regra que teria pego `CLI0001` em nov/2025**, 10 meses antes da baixa |
| **A12** | Titulo a > 300 dias de vencimento nao pago (vira baixa em 365d) | — | atingido | pre-alerta de perda; R$ 664 mil ja baixados como Perda Cobravel |

### 8.3 Margem e frota (paginas 4 e 5)

| ID | Regra | Ambar | Vermelho | Situacao em REF |
|---|---|---|---|---|
| **A13** | Margem acumulada do contrato (periodo casado) | < 15% | **< 0%** | **4 vermelhos reais** (`CTR0151`, `CTR0119`, `CTR0041`, `CTR0121`) + `CTR0023` marcado como artefato; ambar: `CTR0110` 7,3%, `CTR0057` 11,5%, `CTR0113` 14,5% |
| **A14** | Corretiva ÷ custo total do veiculo em 3 meses consecutivos | ≥ 25% | ≥ 40% | faixa **7+ anos: 29,5% agregado** → 45 veiculos candidatos a renovacao |
| **A15** | Taxa de ociosidade da frota no mes | ≥ 4% | ≥ 6% | **ago/26 6,3% → VERMELHO**; nov/25 6,7%, fev/26 6,4%, jul/26 4,6% |
| **A16** | Custo de ociosidade 12m ÷ custo operacional 12m | ≥ 2,5% | ≥ 4% | **2,7% → AMBAR** |
| **A17** | Margem do segmento < margem consolidada − 5 p.p. | atingido | − 10 p.p. | Varejo e Distribuicao **24,2%** (−10,1 p.p. vs 34,3%) → vermelho; Servicos Publicos 29,2% → ambar |

### 8.4 Qualidade de dado (barra discreta, todas as paginas)

| ID | Regra | Situacao em REF |
|---|---|---|
| **A18** | Titulos com `data_baixa` posterior a REF | **4 titulos, R$ 182 mil** |
| **A19** | Cancelamento por "Erro de Emissao" + "Faturamento Indevido" ÷ faturamento | **R$ 1,774 mi = 2,0% do faturado** → falha de processo, nao comercial |
| **A20** | Contratos com margem calculada sobre < 2 meses de receita | 6 contratos → excluir de rankings |

---

## 9. Contrato para a equipe

### 9.1 Arquiteto de dados (`frotas/metrics/`, `docs/02_*`) — precisa implementar

- **Uma funcao por metrica canonica de §3**, todas parametrizadas por `:ref`, `:ini`, `:fim` e pelos filtros de §7:
  `faturamento_bruto`, `faturamento_valido`, `receita_liquida`, `custo_operacional`, `margem_operacional`,
  `inadimplencia_30d_pit`, `recebimento_caixa`, `aging_carteira`, `custo_ociosidade`, `taxa_ociosidade`,
  `margem_por_contrato` (periodo casado), `curva_abc`, `recuperacao_vencidos`, `uso_limite_credito`.
- **`inadimplencia_30d_pit(:ref)` com denominador de janela fixa de 12 meses de competencia** e filtro PIT de
  cancelamento nos **dois** lados. E a funcao mais critica do app; testar contra 3,558 / 6,471 / 10,204 / 9,368 / 10,021.
- **`metas_do_periodo(tipo_meta, :ini_ym, :fim_ym, nivel, chave)`** aplicando `eh_versao_vigente = true` **sempre** e
  `tipo_agregacao`: `Soma` → soma das mensais; `Media Ponderada` → `sum(meta_RL − meta_Custo)/sum(meta_RL)`;
  `Fim de Periodo` → meta do ultimo `ano_mes`. Deve retornar `NULL` (nao zero) quando o recorte nao tem meta.
- **Guarda-corpo de recorte**: quando um filtro dimensional esta ativo, `custo_operacional` e `margem_operacional`
  devem retornar a variante ex-ocioso **com uma flag** `escopo='contratos'` para a UI renomear o KPI.
- **Guarda-corpo de efeito base**: `inadimplencia_30d_pit` retorna `NULL` + `motivo='janela_incompleta'` para
  `:ref < '2025-01-31'`.
- **`margem_por_contrato` com periodo casado** e coluna `meses_com_receita`; contratos com `meses_com_receita < 2`
  vem marcados `periodo_parcial = true`.
- **Suite de testes de regressao** com os 24 numeros de §2.1 como valores esperados (tolerancia 0,01%). Se um quebrar,
  o app nao sobe.
- Uma **view/CTE de calendario de referencia** com os fins de mes de `2024-01-31` a `2026-08-31` para as series PIT
  (evita `generate_series` espalhado pelas paginas). Atencao: `data_vencimento <= :ref - 30` exige cast de `date`.
- Tudo **somente SELECT**; cache por `(metrica, filtros, ref)` — as consultas PIT sao O(n) por ponto da serie.

### 9.2 Especialista de UX / dataviz (`docs/03_*`, `frotas/ui/`) — precisa visualizar

- **Header de 6 KPIs** (P1-P6) repetido em todas as paginas: valor grande, meta vigente, desvio em `%` (BRL) ou `p.p.`
  (percentuais), sinal de cor pelo limiar de §8. P6 sem gauge (nao tem meta).
- **Serie de inadimplencia PIT com a meta sobreposta** e **jan/2024-dez/2024 em cinza tracejado** com legenda
  "janela de 12 meses incompleta". Marcar out/2025 como ponto de inflexao (+2,87 p.p. no mes).
- **Aging em barras empilhadas horizontais** com as 6 faixas, ordenadas por severidade, valor em R$ e % ao lado;
  clique na faixa filtra a lista de clientes.
- **Ponte (waterfall) realizado→meta** na pagina 1, decompondo o desvio por segmento — com o aviso de mix de §7.1.
- **Curva ABC** como Pareto (barras + linha acumulada) com corte visivel em 50% e 80%.
- **Scatter risco de cliente**: eixo x = faturamento 12m, eixo y = % vencido do proprio faturamento, tamanho = vencido
  em R$, cor = rating. Quadrante superior direito = os 8 vermelhos de A7. **`CLI0001` precisa saltar da tela.**
- **Heatmap segmento x mes** da inadimplencia PIT — e onde Construcao Civil (5,32 → 20,24%) conta a historia sozinha.
- **Barras de corretiva por faixa de idade** com o valor por veiculo-ano (8,9 → 23,2 mil) e a economia anual estimada.
- **Serie de ociosidade** com duplo eixo (veiculos parados x custo) e banda de alerta em 4% e 6%.
- **Badges obrigatorios**: `escopo: contratos` quando ha filtro dimensional na margem/custo; `foto em <data>` nos cards
  de carteira; `meta indisponivel neste recorte`; `periodo parcial` nas linhas de contrato.
- **Formatacao pt-BR sem excecao**: `R$ 1.234.567`, `R$ 3,19 mi`, `34,7%`, `+1,22 p.p.`, `2026-08` como `ago/26`.
  Cor: vermelho **so** para limiar vermelho de §8; ambar para ambar; verde apenas para desvio favoravel confirmado.
- **Regra editorial**: toda tela que compara com meta deve deixar obvio o periodo da meta usada. Os erros D2 e D3 de
  §2.2 nasceram exatamente de comparar 8 meses com meta anual — e o D3 chega a **inverter o sinal do desvio**.
