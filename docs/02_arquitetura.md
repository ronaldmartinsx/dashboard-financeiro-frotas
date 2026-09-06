# 02 — Arquitetura de dados e seguranca

Documento do **Arquiteto de Dados e Seguranca**. Cobre a camada de acesso
(`frotas/config.py`, `frotas/db.py`), a camada semantica (`frotas/metrics/`), o
objeto de filtros (`frotas/filtros.py`), a estrategia de cache e o modelo de
seguranca. O engenheiro front-end consome **apenas** o que esta na secao
"Contrato das funcoes publicas" — nao ha SQL fora de `frotas/`.

Fonte de verdade de negocio: `DICIONARIO_DADOS.md` e `docs/00_briefing_tecnico.md`.
Todos os numeros deste documento sao reproduzidos por `scripts/validar_metricas.py`.

---

## 1. Camadas

```
                       ┌──────────────────────────────────────────┐
   streamlit_app.py    │  views/*.py  (paginas, st.Page)          │   nao escrevem SQL
   (entrypoint)        │  frotas/ui/  (tema, formatacao BR)       │   nao importam frotas.db
                       └───────────────┬──────────────────────────┘
                                       │ Filtros (frozen dataclass, hashavel)
                                       ▼
                       ┌──────────────────────────────────────────┐
                       │  frotas/metrics/                         │   CAMADA SEMANTICA
                       │    receita · credito · custos            │   1 funcao = 1 metrica
                       │    metas · dimensoes · alertas           │   devolve DataFrame
                       │  frotas/filtros.py  (Filtros -> WHERE)   │   pronto para plotar
                       └───────────────┬──────────────────────────┘
                                       │ consultar(sql, params, ttl)
                                       ▼
                       ┌──────────────────────────────────────────┐
                       │  frotas/db.py                            │   CAMADA DE ACESSO
                       │    guarda SELECT/WITH                    │   unica porta de leitura
                       │    st.cache_data (3 faixas de TTL)       │
                       │    st.cache_resource -> Engine           │
                       │  frotas/config.py (segredos, constantes) │
                       └───────────────┬──────────────────────────┘
                                       │ SQLAlchemy 2.0 + psycopg2
                                       │ sslmode=require · AUTOCOMMIT
                                       │ default_transaction_read_only=on
                                       ▼
                       ┌──────────────────────────────────────────┐
                       │  Supavisor (pooler, modo session, :5432) │
                       │  Postgres 17.6 / Supabase                │
                       │  schema public — 8 tabelas, estrela      │
                       └──────────────────────────────────────────┘
```

Regras de dependencia (respeitadas no codigo entregue):

* `views/` e `frotas/ui/` **nao** importam `frotas.db`. Se uma pagina precisa de
  um numero novo, a metrica nasce em `frotas/metrics/`, com docstring e
  verificacao no validador.
* `frotas/metrics/` **nao** monta string de valor: todo filtro vai por bind param.
* `frotas/db.py` nao conhece negocio; `frotas/metrics/` nao conhece conexao.

---

## 2. Camada de acesso

### 2.1 Segredos (`frotas/config.py`)

Precedencia, do mais forte para o mais fraco:

| # | Origem | Quando |
|---|---|---|
| 1 | `st.secrets` (raiz ou secao `[conexao]`) | deploy (Community Cloud / container) |
| 2 | variavel de ambiente | CI, execucao headless de `scripts/` |
| 3 | `.env` na raiz | desenvolvimento local |

`obter_segredo(nome)` percorre as tres na ordem. `obter_dsn()` valida o formato e
levanta `CredencialAusente` com uma mensagem que diz **onde configurar**, jamais o
valor. `origem_segredo()` / `diagnostico_segredos()` devolvem so a *origem* —
usados pela sidebar de diagnostico sem risco de vazamento.

O `.env` e lido com `dotenv_values()`, que **nao** escreve em `os.environ` — o
segredo nao vaza para processos filhos.

### 2.2 Engine (`frotas/db.py::obter_engine`)

Cacheado com `st.cache_resource` (um engine por processo). Parametros e por que:

| Parametro | Valor | Motivo |
|---|---|---|
| `pool_size` / `max_overflow` | 3 / 2 | o pooler e recurso compartilhado do projeto; o app e de leitura e cacheado, nao precisa de mais |
| `pool_pre_ping` | `True` | o Supavisor derruba conexao ociosa em silencio; sem pre-ping a primeira consulta apos a pausa falha |
| `pool_recycle` | 240 s | recicla antes do corte do pooler |
| `pool_timeout` | 15 s | falha rapido em vez de pendurar a UI |
| `connect_timeout` | 10 s | teto do handshake TCP/TLS |
| `sslmode` | `require` | trafego sempre cifrado |
| `isolation_level` | `AUTOCOMMIT` | leitura pura nao precisa de `BEGIN`/`COMMIT`: economiza 2 round-trips por consulta (~480 ms medidos) |

**Ajustes de sessao.** O Supavisor **descarta** o startup packet `options`
(verificado: `application_name` chegava como `Supavisor`, `statement_timeout`
como `2min` e `default_transaction_read_only` como `off`). Por isso um listener
`connect` reaplica tudo via `set_config(..., false)` — parametrizado, porque
`SET` puro nao aceita bind param:

```
application_name                     = frotas-data-app
statement_timeout                    = 30000 ms
idle_in_transaction_session_timeout  = 30000 ms
default_transaction_read_only        = on
```

O validador confere os quatro a cada execucao.

### 2.3 Execucao (`consultar`)

```python
consultar(sql: str, params: Mapping[str, Any] | None = None, ttl: int = TTL_FATOS) -> pd.DataFrame
```

* **Guarda de leitura** (`validar_sql_leitura`): sobre o texto **sem comentarios**,
  exige inicio em `SELECT`/`WITH`, recusa verbo de escrita/DDL e recusa `;` que
  emende um segundo comando. Roda duas vezes: antes de consultar o cache e
  novamente antes do round-trip.
* **Parametrizacao total**: valores viajam como `:nome`. Listas viram bind
  `expanding` do SQLAlchemy automaticamente (`... in :segmentos`), entao nem
  filtro multi-selecao precisa de f-string.
* **Chave de cache estavel**: `_normalizar_params` converte o dicionario numa
  **tupla ordenada de pares** (listas viram tuplas ordenadas). `{"b":[2,1],"a":x}`
  e `{"a":x,"b":[1,2]}` produzem a mesma chave — verificado no validador.
* **Erros tipados** com `mensagem_usuario` pronta para `st.error`:
  `ErroConexao` (credencial/rede/pooler), `ErroConsulta` (timeout, read-only),
  `SqlNaoPermitido` (guarda). Stack trace nunca chega a tela; DSN nunca aparece
  em mensagem.
* **Degradacao**: `verificar_conexao() -> EstadoConexao(ok, mensagem, origem_credencial)`
  para o boot do app. Sem credencial, devolve `ok=False` com instrucao de
  configuracao — nao levanta.

Uso na UI:

```python
estado = db.verificar_conexao()
if not estado.ok:
    st.error(estado.mensagem)
    st.stop()
```

---

## 3. Filtros compartilhados (`frotas/filtros.py`)

`Filtros` e um `dataclass(frozen=True)` — imutavel e hashavel, porque entra na
chave de cache. Use `Filtros.criar(**kwargs)` (aceita listas dos widgets) e
`f.com(segmentos=[...])` para derivar variantes.

Campos: `competencia_ini`, `competencia_fim`, `data_ref`, `segmentos`, `portes`,
`ratings`, `ufs`, `clientes`, `tipos_receita`, `tipos_contrato`,
`status_contrato`, `categorias_veiculo`, `categorias_custo`, `tipos_custo`,
`incluir_cancelados`.

Propriedades uteis: `f.ref` (data de referencia efetiva, padrao 2026-08-31),
`f.inicio` / `f.fim` (competencia efetiva), `f.tem_recorte_cliente`.

### 3.1 Que metrica ignora que filtro, e por que

`frotas.filtros.politica_filtros()` devolve esta tabela como DataFrame — mostre-a
na UI quando um recorte "nao pegar".

| Metrica | Ignora | Motivo |
|---|---|---|
| `credito.inadimplencia_ponto_no_tempo` (denominador) | `competencia_ini/fim` | o denominador e a **janela movel fixa de 12 meses** contada de `data_ref`. Deixar a tela mexer nela quebra a comparabilidade com o publicado e com a serie historica. |
| `inadimplencia_ponto_no_tempo` (numerador), `aging_carteira`, `aging_por_cliente`, `risco_por_*`, `titulos_em_risco_de_baixa`, `titulos_com_baixa_futura` | `competencia_ini/fim` | sao **fotos da carteira inteira** numa data. Um titulo de 2024 ainda vencido conta na foto de 2026; recortar por competencia esconderia justamente o atraso antigo. |
| `custos.custo_ociosidade` | `segmentos`, `portes`, `ratings`, `ufs`, `clientes`, `tipos_contrato`, `status_contrato` | armadilha 6: `custos.id_contrato IS NULL` nao tem cliente nem segmento. Aplicar o recorte **zeraria** a metrica em vez de filtra-la. |
| `custos.custos_por_competencia/ano/dimensao` | nenhum, mas **trocam de fonte** | sem recorte, o custo inclui o ocioso (e assim reproduz 18,3 / 21,5 / 15,6 mi). **Com** recorte de cliente ou de contrato a fonte muda para custo alocado, `custo_ocioso_incluido` volta `False` e `escopo` vira `'contratos'` — a UI deve exibir esse aviso. |
| `receita.faturamento_por_categoria_veiculo` | nenhum, mas **rateia** | titulo nao tem veiculo. A receita e dividida em partes iguais entre os veiculos alocados ao contrato na competencia do titulo. Colunas com sufixo `_rateado`/`_rateada`. |
| `metas.*` | tudo, exceto `nivel`/`chave` (segmento) e o ano | a tabela `metas` so tem os niveis Empresa e Segmento. Filtrar o realizado sem filtrar a meta inventaria variacao. |
| `dimensoes.*` | todos | listas de filtro mostram o dominio completo; senao o usuario fica preso num recorte vazio. |

---

## 4. Contrato das funcoes publicas

Todas recebem `Filtros` (ou os parametros de meta) e devolvem `pandas.DataFrame`.
Nomes de coluna sao estaveis — sao o contrato com o front-end.

### 4.0 O escopo do app sao cinco eixos, e so eles

1. **Faturamento** · 2. **Recebimento** · 3. **Inadimplencia — somente a posicao
atual** (o saldo em aberto na data de referencia) · 4. **Metas** (realizado x
meta) · 5. **Custos**.

**O que saiu da camada semantica** (decisao do dono do projeto — nao reabrir):

| Saiu | Onde estava | Consequencia |
|---|---|---|
| **Margem Operacional**, por completo | `custos.margem_por_competencia/ano/contrato/veiculo/categoria_veiculo`, `contratos_deficitarios`, a linha de Margem em `metas.*` | A metrica existe no banco, **nao neste projeto**. `metas.TIPOS_META` tem **5** entradas; pedir `'Margem Operacional'` levanta `ValueError`. Com ela saiu a agregacao `Media Ponderada`, que era exclusiva dela. |
| **Inadimplencia retroativa / serie historica** | `credito.serie_inadimplencia`, `serie_inadimplencia_por_dimensao`, `serie_inadimplencia_por_segmento` (heatmap), `serie_vencido_por_cliente`, `clientes_saindo_de_zero`, `recuperacao_credito`, `recuperacao_por_safra`, `recuperacao_global`, `atraso_medio_ponderado` | O eixo 3 e **a foto**, nao a linha do tempo. `inadimplencia_ponto_no_tempo` continua aceitando qualquer `data_ref` — a UI pode mudar a data, mas nao plotar a serie. |
| **Secao de cancelamentos** | `receita.cancelamentos_por_competencia`, `cancelamentos_por_motivo` | Vira **nota de rodape** do visual de faturamento, alimentada por `valor_cancelado` / `pct_cancelado`, que continuam em `resumo`, `faturamento_por_competencia` e `faturamento_por_ano`. **A logica point-in-time de cancelamento nao saiu**: e a armadilha 1 e continua separando `faturamento_bruto` de `faturamento_valido`. |
| **Concentracao / curva ABC** | `credito.curva_abc_clientes` | Substituida por `receita.top_clientes(f, limite=10)`. |
| **Carteira contratual** | `receita.contratos_ativos`, `carteira_contratos`, `churn_contratual` | MRR e churn saem do app. |
| **Manutencao corretiva** | `custos.corretiva_por_faixa_idade`, `serie_corretiva_por_veiculo`, `veiculos_corretiva_recorrente`, a coluna `pct_corretiva` | Do eixo de custos fica a quebra por categoria (`custos_por_dimensao`), onde a corretiva continua visivel como uma categoria. |
| **7 alertas** | A2, A5, A11, A13, A14, A17, A20 | Sobram **13**. Ver §4.6. |

**Uma funcao virou privada por dependencia**, em vez de ser removida:
`receita._cancelamentos_por_motivo` — e a unica fonte do alerta **A19**
(cancelamento por falha de processo, `Erro de Emissao` + `Faturamento Indevido`).
Nao esta no contrato: a UI **nao** deve chama-la; o numero chega pronto em
`alertas.avaliar()`.

Nenhuma outra funcao removida era dependencia interna de uma preservada.

### 4.1 `frotas.metrics.dimensoes` — TTL 24 h

| Funcao | Devolve |
|---|---|
| `opcoes_filtros() -> dict[str, list[str]]` | **use esta no boot**: 15 dominios em 1 round-trip (`segmentos`, `portes`, `ratings`, `ufs`, `categorias_veiculo`, `status_veiculo`, `tipos_receita`, `motivos_cancelamento`, `motivos_baixa`, `formas_pagamento`, `tipos_contrato`, `status_contrato`, `categorias_custo`, `tipos_custo`, `tipos_meta`) |
| `listar_segmentos/portes/ratings/ufs/categorias_veiculo/tipos_receita/tipos_contrato/status_contrato/categorias_custo/tipos_custo/motivos_cancelamento/motivos_baixa/tipos_meta() -> list[str]` | um dominio cada (1 round-trip cada — evite em serie) |
| `listar_clientes()` | `id_cliente, nome_cliente, segmento, porte, rating_credito, uf, limite_credito` |
| `intervalo_competencia() -> (Timestamp, Timestamp)` | primeira e ultima competencia com fato (2024-01-01 .. 2026-08-01) |
| `calendario_meses()` | `competencia, ano_mes, ano, trimestre` |

O modulo ficou **inteiro**: `tipos_meta` continua devolvendo os 6 valores do
banco (Margem Operacional inclusive), porque e o dominio da coluna, nao o
contrato do app. Quem monta seletor de meta deve usar `metas.TIPOS_META`, que tem
os 5 em escopo.

### 4.2 `frotas.metrics.receita` — TTL 1 h  ·  eixo 1 (faturamento)

| Funcao | Colunas devolvidas |
|---|---|
| `resumo(f)` | `faturamento_bruto, faturamento_valido, receita_liquida, impostos, valor_cancelado, qtd_titulos, pct_cancelado, ticket_medio` (1 linha) |
| `faturamento_por_competencia(f)` | `competencia, ano_mes, ano, faturamento_bruto, faturamento_valido, receita_liquida, impostos, valor_cancelado, qtd_titulos` |
| `faturamento_por_ano(f)` | idem + `meses, eh_parcial` |
| `faturamento_por_dimensao(f, dimensao, limite=None)` | coluna da dimensao + as medidas + `participacao_pct`. `dimensao` ∈ `segmento, porte, rating, uf, cliente, tipo_receita, tipo_contrato, status_contrato, contrato, categoria_veiculo` |
| `faturamento_por_categoria_veiculo(f)` | `categoria, faturamento_bruto_rateado, receita_liquida_rateada, faturamento_valido_rateado, qtd_veiculos, participacao_pct` |
| `yoy_mensal(f)` | `competencia, ano_mes, ano, mes, faturamento_bruto, faturamento_bruto_ano_anterior, receita_liquida, receita_liquida_ano_anterior, variacao_abs, variacao_pct` |
| `yoy_anual(f)` | `ano, meses, faturamento_bruto, receita_liquida, faturamento_bruto_ano_anterior, faturamento_bruto_ano_anterior_comparavel, eh_parcial, variacao_pct, variacao_pct_comparavel` |
| `top_clientes(f, limite=10)` | `id_cliente, nome_cliente, segmento, porte, rating_credito, faturamento_bruto, receita_liquida, qtd_titulos, participacao_pct` — **o top 10 que substituiu a curva ABC** |

**Para o grafico use `variacao_pct_comparavel` em 2026**, nunca `variacao_pct`:
o ano tem 8 meses (armadilha 7). Contra o ano cheio de 2025 da −29,7%; contra os
mesmos 8 meses, +5,9%.

**A nota de rodape de cancelamento** sai de `resumo` / `faturamento_por_*`:
`valor_cancelado` e `pct_cancelado` no periodo, e a diferenca entre
`faturamento_bruto` e `faturamento_valido` na data de referencia. Sao 3,53%
(2024), 6,23% (2025) e 1,97% (2026) do faturamento — ver a divergencia de
definicao em §5.4.

### 4.3 `frotas.metrics.credito` — TTL 6 h (point-in-time) / 1 h (resto)

Eixo 3 (**posicao atual** da inadimplencia) e eixo 2 (recebimento).
**Nao existe serie historica de inadimplencia neste contrato.** Toda funcao aqui
e uma foto em `data_ref`; a UI muda a data, nao plota a linha do tempo.

| Funcao | Colunas devolvidas |
|---|---|
| `inadimplencia_ponto_no_tempo(f, data_ref=None)` | `data_ref, valor_vencido_30d, qtd_titulos_vencidos, faturamento_bruto_12m, janela_ini, janela_fim, inadimplencia_pct, janela_completa` (1 linha) — **o coracao do eixo 3** |
| `aging_carteira(f, data_ref=None)` | `faixa, valor_bruto, qtd_titulos, participacao_pct` (ordem: A vencer · 1-30d · 31-60d · 61-90d · 91-180d · 180+d) |
| `aging_por_cliente(f, data_ref=None, limite=None)` | `id_cliente, nome_cliente, segmento, porte, rating_credito, limite_credito` + uma coluna por faixa + `carteira_total, vencido_30d_mais, pct_vencido_30d, uso_limite_pct` |
| `risco_por_rating(f, data_ref=None)` | `rating_credito, qtd_clientes, carteira_total, vencido_30d_mais, faturamento_bruto_12m, inadimplencia_pct, pct_vencido_30d` |
| `risco_por_segmento(f, data_ref=None)` | `segmento` + as mesmas medidas |
| `risco_por_cliente(f, data_ref=None, limite=20)` | `id_cliente, nome_cliente, segmento, porte, rating_credito, limite_credito, carteira_total, vencido_30d_mais, faturamento_bruto_12m, inadimplencia_pct, pct_vencido_30d, uso_limite_pct` |
| `titulos_do_cliente(f, id_cliente, data_ref=None)` | `id_titulo, id_contrato, tipo_receita, descricao, competencia, ano_mes, data_emissao, data_vencimento, valor_bruto, valor_liquido, data_pagamento, valor_pago, valor_juros_multa, dias_atraso, faixa, status_calculado, status_titulo_gravado, forma_pagamento, motivo_cancelamento, motivo_baixa` — **a unica funcao com grao de titulo** |
| `titulos_em_risco_de_baixa(f, data_ref, dias_limite=300)` | `id_titulo, id_cliente, nome_cliente, segmento, rating_credito, competencia, data_vencimento, dias_vencido, valor_bruto` — alerta A12 |
| `titulos_com_baixa_futura(f, data_ref=None)` | `id_titulo, id_cliente, nome_cliente, data_vencimento, data_baixa, motivo_baixa, valor_bruto` — alerta A18 |
| `cobertura_de_caixa(f, data_ref=None)` | `data_ref, janela_ini, janela_fim, recebimento_12m, recebimento_sem_juros_12m, faturamento_valido_12m, cobertura_pct` — **92,5%**; e o KPI do **eixo 2**. `recebimento_12m` e o caixa de verdade (32,958 mi, **com** juros) e alimenta o cartao; a razao usa `recebimento_sem_juros_12m` (32,490 mi), porque o denominador nao tem juros |

`janela_completa=False` antes de dez/2024: a janela de 12 meses do denominador
ainda esta incompleta e o percentual sobe por construcao (armadilha 5). Marque
isso na tela quando o usuario recuar a data de referencia.

As somas fecham: `risco_por_rating` e `risco_por_segmento` reproduzem, somadas, o
`valor_vencido_30d` de `inadimplencia_ponto_no_tempo` (3,5195 mi em 2026-08-31) —
mas a **razao** de cada linha e a do proprio recorte, entao a media das linhas
**nao** e a inadimplencia da empresa.

### 4.4 `frotas.metrics.custos` — TTL 1 h  ·  eixo 5 (custos)

| Funcao | Colunas devolvidas |
|---|---|
| `custos_por_competencia(f)` | `competencia, ano_mes, ano, custo_total, custo_alocado, custo_ocioso, custo_fixo, custo_variavel, custo_nao_caixa, qtd_veiculos, custo_ocioso_incluido, escopo` |
| `custos_por_ano(f)` | idem + `meses, eh_parcial` |
| `custos_por_dimensao(f, dimensao)` | coluna da dimensao + as medidas + `participacao_pct, custo_ocioso_incluido, escopo`. `dimensao` ∈ `categoria_custo, tipo_custo, categoria_veiculo, marca_modelo, veiculo` |
| `custo_ociosidade(f)` | `competencia, ano_mes, custo_ocioso, qtd_veiculos_ociosos, qtd_veiculos_frota, taxa_ociosidade_pct, custo_total, pct_do_custo_total` |

`escopo` (`'empresa'` / `'contratos'`) e o rotulo que a UI usa: com recorte de
cliente ou de contrato a fonte muda para o custo **alocado**, o patio some,
`custo_ocioso_incluido` volta `False` e o numero deixa de ser comparavel com a
meta — renomeie o KPI para **Custo de Contratos** e esconda o gauge.

Manutencao Corretiva continua visivel como **uma categoria** de
`custos_por_dimensao('categoria_custo')`; o que saiu foi a analise dedicada
(faixa de idade, recorrencia por veiculo).

### 4.5 `frotas.metrics.metas` — TTL 1 h / 6 h  ·  eixo 4

| Funcao | Colunas devolvidas |
|---|---|
| `comparativo_anual(ano, nivel="Empresa", chave="TOTAL", tipos=None, base="alinhada")` | `tipo_meta, unidade, tipo_agregacao, versao_meta, meses_realizados, periodo_realizado, eh_parcial, realizado, meta_alinhada, meta_anual, meta_comparavel, base_comparacao, variacao_abs, variacao_pct` (+ `variacao_*_alinhada` e `variacao_*_anual`) |
| `serie_mensal(tipo_meta, ano, nivel, chave)` | `ano_mes, realizado, meta, variacao_abs, variacao_pct, unidade, tipo_agregacao, versao_meta` |
| `comparativo_por_segmento(tipo_meta, ano)` | `segmento, realizado, meta_alinhada, meta_anual, meta_comparavel, variacao_abs, variacao_pct, meses_realizados` |
| `realizado_mensal(tipo_meta, ano=None, nivel, chave)` | `ano_mes, realizado` |
| `metas_do_ano(ano, nivel, chave)` | `tipo_meta, granularidade, ano_mes, trimestre, meta, unidade, tipo_agregacao, versao_meta` (1 round-trip para o ano inteiro) |
| `metas_mensais(...)` / `meta_anual(...)` | recortes em memoria de `metas_do_ano` |
| `versoes_orcamento(ano=None)` | `ano, versao_meta, eh_versao_vigente, tipo_meta, valor_meta_anual, unidade` — as duas versoes de 2026 lado a lado |

**`TIPOS_META` tem 5 entradas**: `Faturamento`, `Receita Liquida`,
`Recebimento (Caixa)`, `Custo Operacional`, `Inadimplencia > 30d`.
**Margem Operacional nao aparece na tabela de metas do app** — pedi-la em `tipos`
levanta `ValueError`. `SO_EMPRESA` (metricas sem recorte por segmento, armadilha
6) ficou com `Custo Operacional` e `Inadimplencia > 30d`; `comparativo_por_segmento`
aceita as outras tres.

Sobraram **duas** agregacoes: `Soma` (as quatro metricas em BRL) e `Fim de Periodo`
(Inadimplencia, que vale o valor do ultimo mes do periodo). `Media Ponderada` era
exclusiva da Margem e saiu com ela.

`comparativo_anual` aceita `base='alinhada'` (padrao) ou `'anual'`, e devolve
**as duas leituras sempre**: `variacao_abs_alinhada` / `variacao_pct_alinhada` e
`variacao_abs_anual` / `variacao_pct_anual`. Em 2026 elas divergem — ver §5.3.

Numeros que o validador prende: 2025 faturamento **+6,8%**, recebimento
**−2,9%**, inadimplencia **+7,20 p.p.**; 2026 (8m) faturamento +2,9% contra a
meta jan-ago de 23,92 mi.

### 4.6 `frotas.metrics.alertas` — TTL herdado das metricas

| Funcao | Devolve |
|---|---|
| `avaliar(f=None, data_ref=None, ids=None)` | uma linha por alerta em escopo: `id, categoria, pagina, titulo, nivel, valor, unidade, limiar_ambar, limiar_vermelho, direcao, qtd_vermelho, qtd_ambar, entidades, detalhe, regra` |
| `resumo(f=None, data_ref=None)` | `dict` com `vermelho, ambar, ok, indisponivel, nivel_geral` — o badge do cabecalho |
| `limiares()` | `id, categoria, pagina, titulo, unidade, direcao, ambar, vermelho, regra` — a tabela de limiares, publicavel na UI |

**Sao 13 regras**, nao 20: sairam **A2, A5, A11, A13, A14, A17 e A20**, todas
dependentes de metricas que o projeto nao tem mais (serie historica de
inadimplencia, margem operacional, corretiva recorrente). Ficaram
**A1, A3, A4, A6, A7, A8, A9, A10, A12, A15, A16, A18, A19** — os identificadores
**nao** foram renumerados, para preservar a rastreabilidade com `01_kpis.md` §8.

`nivel` ∈ `ok · ambar · vermelho · indisponivel`. **`indisponivel` nao e falha**:
e a regra dizendo que nao se aplica ao recorte — A1/A3/A6 com filtro dimensional
(essas metas so existem no nivel Empresa) e A15/A16 com recorte de cliente (custo
ocioso nao tem cliente). Renderize cinza com o `detalhe`, nunca verde.

A UI **nao precisa conhecer nenhum limiar**: eles vem em `limiar_ambar` /
`limiar_vermelho` para desenhar bandas (é o que a serie de ociosidade faz em 4% e
6%). Nenhuma das 13 regras restantes tem estado — as tres que tinham (A2, A11,
A14) sairam com o escopo.

Situacao em 2026-08-31 sem filtro, conferida pelo validador: **4 vermelhos**
(A7 com 8 clientes, A8 com 13, A12, A15 com ociosidade de 6,3%), **7 ambar**
(A1 +1,22 p.p., A4 92,5%, A9 1,84x, A10, A16 2,7%, A18, A19 1,98%) e **2 ok**
(A3, A6).

**Como ler `variacao`**: metrica em `BRL` -> use `variacao_pct` (%); metrica em
`%` -> use `variacao_abs`, ja em **pontos percentuais** (`variacao_pct` vem `NaN`
de proposito). `base_comparacao` diz contra o que a variacao foi calculada.

---

## 5. Definicoes canonicas (o que reproduz os numeros publicados)

| Metrica | Definicao que reproduz o publicado | Definicao errada mais comum |
|---|---|---|
| Faturamento bruto | `sum(valor_bruto)` por **competencia**, incluindo cancelados | agrupar por `data_emissao` (desloca 1 mes) |
| Faturamento valido | idem, com `data_cancelamento IS NULL OR > :ref` | usar `status_titulo` (foto de 2026-08-31) |
| Receita liquida | `sum(valor_liquido)` **incluindo cancelados** → 27,9 / 32,8 / 23,0 mi | excluir cancelados → 26,96 / 30,74 / 22,59 mi (nao e o publicado) |
| Custo operacional | `sum(custos.valor)`, **incluindo** `id_contrato IS NULL` | excluir ocioso → perde 0,30/0,36/0,43 mi/ano |
| Inadimplencia > 30d | numerador `valor_bruto` vencido ha >30d, **nao pago e nao cancelado na `:ref`**; denominador faturamento bruto dos **12 meses de competencia** anteriores, tambem point-in-time | qualquer variante sem o filtro point-in-time: 17–20% em jun/26 contra 9,37% correto |
| Aging | nao pago **e** nao cancelado **e** nao baixado na `:ref` | manter baixados → balde 180+ vai de 0,82 para 1,00 mi |
| Meta `Soma` no ano parcial | soma das metas **dos mesmos meses realizados** | meta anual cheia → −31% em 2026 |
| Meta `Fim de Periodo` | comparada contra a **meta anual** (e assim que o dicionario chega a +2,02 p.p. de inadimplencia em 2026) | somar percentuais |

A linha de **margem operacional** saiu desta tabela junto com a metrica: a
definicao continua registrada no `DICIONARIO_DADOS.md`, mas nao ha codigo que a
implemente neste projeto.

### 5.1 Sutileza do aging (registrada aqui porque nao esta no briefing)

Quatro titulos ja marcados `Baixado` na foto de extracao tem `data_baixa`
**posterior** a 2026-08-31 — a baixa e lancada em `vencimento + 370..430 dias` e,
para vencimentos de ago/set 2025, cai em set/out 2026. Um filtro puramente
point-in-time (`data_baixa IS NULL OR data_baixa > :ref`) os manteria na carteira
e o balde 180+ daria **1,00 mi** em vez dos 0,82 mi publicados.

Regra adotada (`frotas.filtros.clausula_nao_baixado_em`): a baixa registrada no
razao vale a partir da data de extracao. Para `:ref >= 2026-08-31` todo titulo com
baixa sai da carteira; antes disso vale o ponto no tempo. Com isso o aging fecha
casa a casa com o publicado e a soma dos baldes bate exatamente com a carteira
`Em Aberto` (7,6622 mi).

### 5.3 Decisoes de definicao ainda em vigor

| Assunto | Decisao | Por que |
|---|---|---|
| **Base de comparacao com meta** | `comparativo_anual` usa **periodo alinhado** por padrao, e devolve as duas leituras | Decisao do coordenador e adocao D2/D3 do `01_kpis.md`. Em 2026 (8m) a inadimplencia da **+1,22 p.p.** contra a meta de ago (8,80%) e +2,02 p.p. contra a de dez (8,00%). Em anos cheios as duas coincidem. |
| **`escopo`** | coluna (`'empresa'` / `'contratos'`) ao lado de `custo_ocioso_incluido` | Pedido A11 do UX e §9.1. `custo_ocioso_incluido` continua existindo; `escopo` e o rotulo que a UI usa para renomear o KPI para **Custo de Contratos** e esconder o gauge de meta. |
| **Aging vs inadimplencia e a baixa** | mantidas divergentes de proposito | O aging exclui baixados (e assim reproduz 0,82 mi na faixa 180+); a inadimplencia nao os exclui (e assim reproduz 9,37%). Sao R$ 328 mil de diferenca. `titulos_com_baixa_futura` (alerta A18) expoe os 4 titulos, R$ 182 mil, que causam a sutileza. |
| **Erro de SQL** | passou a levantar `ErroConsulta`, nao `ErroConexao` | Um `ProgrammingError`/`DataError` e defeito da camada de metricas. Mascara-lo de "banco indisponivel" manda o desenvolvedor procurar problema de rede inexistente. |

### 5.4 Divergencias que **nao** reproduzem o publicado (e por que)

| Item | Publicado | Obtido | Diagnostico |
|---|---|---|---|
| Cancelamentos % por ano | 4,0 / 6,0 / 2,0 | **3,53 / 6,23 / 1,97** (por competencia) | O `DICIONARIO_DADOS.md` ja registra a divergencia: "os valores brutos batem; a diferenca e de definicao". A leitura alternativa (por **ano de cancelamento**) da 1,22 / 5,45 / 5,88 — mais distante ainda. Adotamos **por competencia**, que e a unica coerente com o denominador de faturamento e a mais proxima do publicado. Marcada `INFO` no validador. |
| Contraprova da armadilha 1 | 18,7% em jun/26 | **18,70%** | **Reconciliado na rodada 2.** A definicao que reproduz tira o filtro de cancelamento dos **dois** lados da fracao e mantem o corte point-in-time de pagamento no numerador. Variantes proximas dao 17,12 / 17,93 / 19,59 / 19,70. Agora e verificacao obrigatoria. |

Nenhum outro numero publicado ficou irreconciliado. As tres divergencias que
restavam em metricas removidas (taxa de recuperacao com corte de maturidade,
contratos de periodo parcial do A20, margem do pior segmento no A17) sairam com
elas — restam **3 verificacoes informativas**, as de cancelamento.

---

## 6. Cache e custo das consultas

### 6.1 Estrategia

| Faixa | TTL | Uso |
|---|---|---|
| `TTL_DIMENSOES` | 24 h | listas de filtro, calendario, clientes |
| `TTL_FATOS` | 1 h | agregacoes de receita, custo, metas |
| `TTL_PESADO` | 6 h | series point-in-time (inadimplencia, aging, risco) |

Tres funcoes cacheadas distintas, uma por faixa (`st.cache_data(ttl=...)`), com
`max_entries=256`. O `ttl` passado a `consultar` seleciona a faixa — nao ha
decorador dinamico, entao nao ha colisao de chave entre faixas.

`st.cache_resource` guarda o **engine** (um por processo). `db.limpar_cache()`
invalida so os dados — bom para um botao "Atualizar dados" sem derrubar o pool.

O dataset e estatico (extracao congelada em 2026-08-31), entao TTL longo nao
mente. Se a base for recarregada, `limpar_cache()` resolve.

### 6.2 A restricao que manda no desenho: vazao do pooler

Sao **duas** penalidades de rede independentes, e a segunda so apareceu na
rodada 2:

1. **Latencia por consulta** — ~240 ms de round-trip; com `AUTOCOMMIT` cada
   consulta custa ~490 ms de piso. Remedio: menos consultas (agrupar em
   `UNION ALL`, `generate_series`, uma query por serie inteira).
2. **Vazao por linha** — o pooler entrega ~**1.000 linhas/s** com 3 colunas e cai
   para ~**200 linhas/s** com 9-10 colunas. Medido: uma grade veiculo x mes de
   6.613 linhas x 9 colunas levou **34 s no cliente** para uma consulta que o
   servidor resolve em **108 ms** (`EXPLAIN ANALYZE`). Remedio: **nao trazer
   grade** — filtrar, agregar ou avaliar a regra no servidor.

Regra pratica para o front-end: **mantenha o resultado abaixo de ~1.000 linhas**.
Acima disso o gargalo deixa de ser o banco e passa a ser o transporte, e nenhum
indice ajuda.

As tres funcoes que avaliavam regra com estado **em SQL** para nao trafegar a
grade (`clientes_saindo_de_zero`, `veiculos_corretiva_recorrente`,
`serie_corretiva_por_veiculo`) sairam com a reducao de escopo, junto com as
series por cliente e por segmento. **O contrato reduzido nao tem nenhuma funcao
que devolva grade**: a maior resposta hoje e `custos_por_dimensao('veiculo')`
com 244 linhas, e a unica de grao de titulo (`titulos_do_cliente`) e sempre
filtrada por um cliente. A regra pratica continua valendo para quem adicionar
metrica nova.

### 6.3 Custo medido

Latencia de rede domina; volume de dados no servidor nao (3.160 titulos, 36.298 custos).

| Consulta | Frio | Quente (cache) |
|---|---|---|
| `select 1` (piso do round-trip) | ~490 ms | — |
| `dimensoes.opcoes_filtros()` (15 dominios, 1 query) | ~3,8 s | ~2 ms |
| `receita.faturamento_por_competencia` / `por_ano` / `yoy_*` | ~0,5 s | ~2 ms |
| `credito.inadimplencia_ponto_no_tempo` | ~0,5 s | ~2 ms |
| `credito.aging_carteira` / `aging_por_cliente` | ~0,5–0,9 s | ~2 ms |
| `receita.faturamento_por_categoria_veiculo` (rateio) | ~0,6 s | ~2 ms |
| `custos.custos_por_dimensao` | ~0,5 s | ~2 ms |
| `metas.comparativo_anual(ano)` (5 metricas, ~6 round-trips) | ~5,5 s | ~5 ms |
| `metas.comparativo_por_segmento` (8 segmentos) | ~8,3 s | ~10 ms |
| `credito.titulos_do_cliente` (drill, 62 linhas) | ~0,6 s | ~2 ms |
| `alertas.avaliar()` (13 regras, ~9 metricas) | ~9 s | ~5 ms |

Otimizacoes ja aplicadas, todas com efeito medido:

1. **`AUTOCOMMIT`** — corta `BEGIN`/`COMMIT`: 950 ms → 490 ms por consulta.
2. **`opcoes_filtros` em 1 `UNION ALL`** — 15 round-trips → 1: 14,2 s → 3,8 s.
3. **`metas_do_ano` em 1 query** — as metas do ano inteiro de uma vez:
   `comparativo_anual` 17,3 s → 6,4 s; `comparativo_por_segmento` 24,3 s → 8,3 s.
4. **Reducao de escopo** — as consultas mais caras da rodada 2 (heatmap de
   inadimplencia por segmento, serie de vencido por cliente, grade de corretiva
   por veiculo) sairam junto com as metricas que as usavam. Nenhuma pagina do
   escopo reduzido passa de ~4 consultas frias.

Recomendacao para o front-end: chame `opcoes_filtros()` **uma vez** no boot (nao
as `listar_*` em serie), prefira `comparativo_anual` a montar a tabela metrica a
metrica, e chame `alertas.avaliar()` **uma vez por render**, reaproveitando o
DataFrame nas paginas (filtre por `pagina`). Nenhuma pagina precisa de mais de
~4 consultas frias.

Indices existentes na base cobrem o que a camada usa: `competencia`,
`data_vencimento`, `data_pagamento`, `status_titulo`, `categoria_custo`.

---

## 7. Seguranca

### 7.1 Modelo de credenciais — o que NUNCA vai para o repositorio

| Segredo | Onde vive | Vai para o git? |
|---|---|---|
| `PG_DSN` | `.env` (local, chmod 600) · `st.secrets` (deploy) | **Nunca** |
| `SUPABASE_PUBLISHABLE_KEY` | idem | **Nunca** (mesmo sendo "publicavel") |
| `SUPABASE_URL` | idem | **Nunca** no `.env`; pode aparecer em doc |

O `.gitignore` ja cobre `.env`. `.env.example` fica versionado **so com as chaves
vazias** — e o contrato de configuracao, nao o segredo.

Garantias no codigo: `config.py` nunca imprime, loga ou escreve valor de segredo;
o `.env` e lido com `dotenv_values()` (nao contamina `os.environ`); mensagens de
erro citam **a origem esperada**, nunca o valor; `diagnostico_segredos()` devolve
so `(nome, origem)`. `db.py` nunca inclui o DSN em texto de excecao — as
mensagens sao pre-escritas, e o `detalhe` guarda so o nome da classe do erro.

**Antes de qualquer publicacao**: `git log -p | grep -i 'postgresql://'` e
`git grep -i 'supabase.co'` devem voltar vazios. Se um segredo ja tiver sido
commitado, rotacione — remover do historico nao basta.

### 7.2 Read-only em profundidade

Quatro barreiras independentes, da mais externa para a mais interna:

1. **Guarda de SQL** (`validar_sql_leitura`): so `SELECT`/`WITH`, sem verbo de
   escrita/DDL, um statement so. Roda antes do cache e antes do round-trip.
2. **Sessao read-only**: `default_transaction_read_only=on` aplicado no `connect`.
   Verificado: `create temp table` volta `cannot execute CREATE TABLE in a
   read-only transaction`.
3. **Timeouts**: `statement_timeout` e `idle_in_transaction_session_timeout` de
   30 s. Uma consulta patologica nao segura conexao do pooler.
4. **Revisao humana**: nenhuma funcao da camada de dados aceita SQL vindo da UI.
   Os unicos identificadores interpolados (`valores_distintos`,
   `faturamento_por_dimensao`, `custos_por_dimensao`) passam por **lista branca**;
   valor livre nunca vira SQL.

O validador exercita as barreiras 1, 2 e 3 a cada execucao (10 verificacoes na
secao `conexao`).

### 7.3 RLS do Supabase e o que a chave publicavel expoe

Estado verificado no projeto `qoirqktsvkeyokyabpgw`:

* RLS **habilitado** nas 8 tabelas de `public`.
* Uma policy por tabela: `leitura publica`, `cmd = SELECT`, `qual = true`, para os
  papeis `anon` e `authenticated`. **Zero** policies de `INSERT`/`UPDATE`/`DELETE`
  — sem policy, a escrita e negada, entao a `SUPABASE_PUBLISHABLE_KEY` da acesso
  de **leitura total** ao dataset e nada alem disso.
* Como a policy e `true` (sem `auth.uid()`), qualquer portador da chave
  publicavel le **todos** os clientes, contratos e titulos. Para um dataset
  sintetico isso e aceitavel e foi decisao do projeto; para dado real seria
  necessario um predicado por tenant/usuario.

Dois pontos de atencao encontrados na auditoria (**nao corrigidos aqui — a tarefa
e read-only**, ficam como recomendacao para o dono do banco):

1. **O `PG_DSN` conecta como `postgres`, que tem `rolbypassrls = true`.** O
   caminho Postgres do app **ignora** as policies de RLS; hoje o unico freio de
   escrita e a sessao read-only + a guarda de SQL desta camada. O correto e criar
   um papel dedicado e trocar o segredo:

   ```sql
   create role app_leitura login password '...' nobypassrls;
   grant usage on schema public to app_leitura;
   grant select on all tables in schema public to app_leitura;
   alter default privileges in schema public grant select on tables to app_leitura;
   alter role app_leitura set default_transaction_read_only = on;
   alter role app_leitura set statement_timeout = '30s';
   ```

2. **Grants de tabela em `public` estao amplos** (`anon` e `authenticated` tem
   `INSERT/UPDATE/DELETE/TRUNCATE` no grant, e so a ausencia de policy os
   bloqueia). Defesa em profundidade recomendada:

   ```sql
   revoke insert, update, delete, truncate on all tables in schema public
     from anon, authenticated;
   ```

   Sem isso, um `alter table ... disable row level security` ou uma policy
   permissiva acidental abre escrita imediatamente.

### 7.4 SQL parametrizado

Nenhum valor de filtro entra por f-string. Valores escalares e datas viajam como
`:nome`; listas de multi-selecao viram bind `expanding` do SQLAlchemy
(`... in :segmentos`). A unica interpolacao que existe e de **identificador**
(nome de coluna de dimensao), e sempre a partir de dicionario fechado no codigo —
`db.valores_distintos` levanta `SqlNaoPermitido` para par `(tabela, coluna)` fora
da lista branca; `receita.faturamento_por_dimensao` e `custos.custos_por_dimensao`
levantam `ValueError` para dimensao desconhecida.

Fragmentos de SQL montados dinamicamente (`condicoes_titulos`,
`condicoes_custos`) so concatenam **texto fixo** do dicionario `_EXPRESSOES` mais
o nome do bind param. O valor nunca aparece na string.

### 7.5 Timeouts

| Timeout | Valor | Onde |
|---|---|---|
| `connect_timeout` | 10 s | handshake TCP/TLS (libpq) |
| `pool_timeout` | 15 s | espera por conexao livre no pool local |
| `statement_timeout` | 30 s | servidor; vira `ErroConsulta` com mensagem amigavel |
| `idle_in_transaction_session_timeout` | 30 s | servidor; impede segurar conexao do pooler |
| `pool_recycle` | 240 s | recicla antes do corte do Supavisor |

### 7.6 Checklist para publicar o app

**Antes do deploy**

- [ ] `git status` limpo e `.env` fora do indice (`git check-ignore -v .env`).
- [ ] `git log -p | grep -iE 'postgresql://|service_role|eyJ'` sem resultado.
- [ ] `requirements.txt` com as versoes fixadas (ja entregue).
- [ ] `python3 scripts/validar_metricas.py` verde (110/110).

**O que muda em `st.secrets`** — crie `.streamlit/secrets.toml` **no painel do
deploy**, nunca no repositorio:

```toml
PG_DSN = "postgresql://<usuario>:<senha>@<host-do-pooler>:5432/postgres"
SUPABASE_URL = "https://<project-ref>.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "<chave publicavel>"
```

Nada mais muda: `config.obter_segredo` ja prefere `st.secrets` a variavel de
ambiente e ao `.env`. Confirme na sidebar que `diagnostico_segredos()` mostra
origem `st.secrets` — se mostrar `.env`, o arquivo vazou para a imagem.

**O que rotacionar**

- [ ] Senha do papel de banco usada no `PG_DSN` — obrigatoriamente, se o DSN
      passou por chat, ticket, log de CI ou pelo `.env` de alguem que saiu.
- [ ] `SUPABASE_PUBLISHABLE_KEY` se ela algum dia foi commitada.
- [ ] Rotacao imediata e sem discussao se uma `service_role key` tiver aparecido
      em qualquer lugar — ela ignora RLS e nao tem uso neste app.
- [ ] Trocar o `PG_DSN` de `postgres` para o papel `app_leitura` da secao 7.3 e
      rotacionar a senha do `postgres` em seguida.

**Depois do deploy**

- [ ] Abrir o app e confirmar que a sidebar mostra "Conectado ao Supabase".
- [ ] Conferir em `pg_stat_activity` que as conexoes aparecem com
      `application_name = 'frotas-data-app'` — e assim que se rastreia o app no
      banco compartilhado.
- [ ] Confirmar que a pagina de erro (derrube o segredo de proposito) mostra a
      mensagem de credencial ausente, **sem stack trace e sem DSN**.

---

## 8. Como rodar a validacao

```bash
python3 scripts/validar_metricas.py              # todas as secoes
python3 scripts/validar_metricas.py --secao credito --secao metas
```

Secoes: `conexao`, `receita`, `credito`, `metas`, `filtros`, `cobranca`, `frota`,
`alertas`. (`carteira`, `margem` e `credito_dim` sairam com as metricas que
verificavam; `cobranca` e `frota` cobrem o que restou dos eixos 2 e 5.)

Saida atual: **110/110 verificacoes obrigatorias OK**, 3 informativas (a
divergencia de definicao dos cancelamentos, §5.4). Codigo de saida 0. O script e
somente leitura e pode ser rodado em CI com `PG_DSN` no ambiente.

Cobertura, por eixo:

| Eixo | O que o validador prende |
|---|---|
| 1 · Faturamento | faturamento bruto e receita liquida por ano (29,8 / 35,0 / 24,6 e 27,9 / 32,8 / 23,0 mi), 2026 marcado parcial, `faturamento_valido = bruto − cancelado` na data ref, cancelamentos por ano (`INFO`), rateio por categoria de veiculo preservando o total, segmentos somando o total |
| 2 · Recebimento | cobertura de caixa 12m **92,5%** (32,491 / 35,120 mi, recebido sem juros), 12 meses de caixa realizado em 2025 |
| 3 · Inadimplencia (foto) | point-in-time em dez/24 **3,56%**, jun/25 **6,47%**, dez/25 **10,20%**, jun/26 **9,37%**; aging em 2026-08-31 (4,47 / 0,76 / 0,44 / 0,40 / 0,77 / 0,82 mi) fechando com a carteira `Em Aberto` (7,6622 mi); contraprova da armadilha 1 (**18,70%** sem o filtro point-in-time); rating e segmento somando o vencido da empresa; o drill ate o titulo de `CLI0001` (159,5 mil, 62 linhas) |
| 4 · Metas | 2024/2025/2026 de Faturamento, Recebimento e Inadimplencia — em especial **2025 +6,8%**, **−2,9%** e **+7,20 p.p.**; meta jan-ago/2026 de 23,92 mi (armadilha 7); as duas versoes de orcamento de 2026 (armadilha 3); Margem Operacional **ausente** do comparativo |
| 5 · Custos | custo operacional por ano (18,3 / 21,5 / 15,6 mi) com ocioso incluido; troca de fonte com recorte de cliente (`escopo='contratos'`); ociosidade dos 4 picos e R$ 612 mil em 12 meses; categorias somando o total |
| Alertas | nivel esperado dos **13** alertas em escopo, as contagens de entidade e a ausencia dos 7 removidos |
| Conexao | as 4 barreiras de read-only e os ajustes de sessao (10 verificacoes) |
