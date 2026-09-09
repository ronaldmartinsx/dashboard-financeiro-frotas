# Briefing tecnico: Data App de Frotas (Streamlit + Supabase)

> **Documento historico, congelado no inicio do projeto (2026-08-31).** Descreve o
> esquema no Postgres e a conexao ao vivo, que saiu em 2026-09-05. O esquema segue
> valido; a secao de conexao nao. Para o estado atual, ver `docs/02_arquitetura.md`.

Documento base lido por **todos** os agentes da equipe. Nao re-descubra o esquema: ele esta aqui.
A fonte de verdade de negocio e `DICIONARIO_DADOS.md` na raiz, leia-o antes de definir qualquer metrica.

## Contexto

Locadora de frotas B2B. Dataset sintetico com narrativas plantadas, periodo de competencia
**2024-01-01 a 2026-08-31** (data de extracao simulada: **2026-08-31**, nenhum pagamento apos ela).
Os dados viviam no Supabase, no schema `public`. Nao existe pasta `data/`.

## Conexao

Credenciais em `.env` na raiz (chmod 600, no `.gitignore`), **nunca** commitar, nunca imprimir valores:

- `PG_DSN`: Postgres via pooler (modo session). E o caminho de leitura do app.
- `SUPABASE_URL` + `SUPABASE_PUBLISHABLE_KEY`: REST anonimo, RLS aplicado, somente leitura.

Regra de seguranca do projeto: **o app e read-only**. Nenhum INSERT/UPDATE/DELETE/DDL em codigo do app.

Ambiente ja instalado (Python 3.13): `streamlit 1.50`, `pandas 2.3`, `plotly 6.3`, `altair 5.5`,
`psycopg2-binary 2.9`, `SQLAlchemy 2.0`, `python-dotenv 1.1`.

## Esquema (public): 8 tabelas, esquema estrela

```
calendario ──┐
             ├── titulos_receber ── contratos ── clientes
clientes ────┘          │              │
                        └── custos ────┤
                              │        │
                          veiculos ── alocacoes_veiculo
metas (tabela isolada, sem FK — junta por ano/ano_mes/trimestre e chave_nivel=segmento)
```

### titulos_receber (3.160): 1 linha = 1 titulo a receber
`id_titulo` `id_contrato` `id_cliente` `tipo_receita` `descricao` `competencia`(date, dia 1)
`data_emissao` `data_vencimento` `valor_bruto` `valor_impostos` `valor_liquido`
`data_pagamento`? `valor_pago`? `valor_juros_multa`? `dias_atraso_pagamento`?(int)
`status_titulo` `data_cancelamento`? `motivo_cancelamento`? `data_baixa`? `valor_baixa`? `motivo_baixa`?
`forma_pagamento`?, `?` = nullable, e o NULL carrega significado (nao pago / nao cancelado).

### custos (36.298): 1 linha = veiculo x mes x categoria
`id_custo` `id_veiculo` `id_contrato`? (NULL = veiculo ocioso) `competencia` `categoria_custo`
`tipo_custo` `valor` `veiculo_ocioso`(bool)

### metas (2.040): 1 linha = versao x metrica x granularidade x recorte
`id_meta` `versao_meta` `eh_versao_vigente`(bool) `tipo_meta` `unidade` `tipo_agregacao`
`granularidade` `nivel_analise` `chave_nivel` `ano` `trimestre`? `ano_mes`?
`data_inicio_periodo` `data_fim_periodo` `valor_meta`
Percentuais em **pontos percentuais** (9.37 = 9,37%).

### clientes (58)
`id_cliente` `nome_cliente` `segmento` `porte` `cidade`? `uf`? `rating_credito`? `limite_credito`? `data_cadastro`?

### contratos (153)
`id_contrato` `id_cliente` `tipo_contrato` `data_inicio` `data_fim_prevista`? `data_fim_efetiva`?
`prazo_meses`? `qtd_veiculos`? `valor_mensal_contratado`? `indice_reajuste`? `prazo_pagamento_dias`? `status_contrato`

### veiculos (245)
`id_veiculo` `placa` `categoria` `marca_modelo` `ano_modelo`? `data_aquisicao`? `valor_aquisicao`?
`valor_residual_estimado`? `vida_util_meses`? `data_venda`? `status_veiculo`? `taxa_locacao_mensal_pct`? `eh_financiado`?

### alocacoes_veiculo (435)
`id_alocacao` `id_contrato` `id_veiculo` `data_alocacao` `data_devolucao`?, M:N com vigencia.

### calendario (1.096): 2024-01-01 a 2026-12-31
`data` `ano` `trimestre` `mes` `mes_nome` `ano_mes` `ano_mes_num` `dia` `dia_semana` `eh_fim_semana` `eh_dia_util`

## Dominios enumerados (valores reais, sem acento no banco)

- `clientes.segmento`: Agronegocio · Construcao Civil · Energia e Saneamento · Industria · Logistica e Transporte · Mineracao · Servicos Publicos · Varejo e Distribuicao
- `clientes.porte`: Grande · Medio · PME  |  `rating_credito`: A · B · C · D
- `contratos.tipo_contrato`: Locacao com Motorista · Locacao Mensal Frota · Locacao Spot · Terceirizacao de Frota
- `contratos.status_contrato`: Ativo · Encerrado · Rescindido  |  `indice_reajuste`: IGP-M · IPCA
- `veiculos.categoria`: Automovel Executivo · Caminhao Munck · Caminhao Toco · Caminhao Truck · Caminhonete 4x4 · Cavalo Mecanico · Onibus Rodoviario · Van / Furgao
- `veiculos.status_veiculo`: Ativo · Vendido
- `titulos_receber.tipo_receita`: Avaria · KM Excedente · Locacao · Multa de Transito · Multa Rescisoria · Servicos Adicionais
- `titulos_receber.status_titulo`: Baixado · Cancelado · Em Aberto · Pago
- `motivo_cancelamento`: Acordo Comercial · Erro de Emissao · Faturamento Indevido · Renegociacao de Contrato · Troca de Veiculo
- `motivo_baixa`: Baixa Caixa · Cortesia · Glosa · Perda Cobravel  |  `forma_pagamento`: Boleto · PIX · TED
- `custos.categoria_custo`: Depreciacao · Despesa Financeira · IPVA e Licenciamento · Manutencao Corretiva · Manutencao Preventiva · Motorista (Mao de Obra) · Overhead Administrativo · Patio e Ociosidade · Pneus · Rastreamento e Telemetria · Seguro
- `custos.tipo_custo`: Fixo · Variavel · Nao Caixa
- `metas.tipo_meta` / `tipo_agregacao` / `unidade`:
  Faturamento/Soma/BRL · Receita Liquida/Soma/BRL · Recebimento (Caixa)/Soma/BRL ·
  Custo Operacional/Soma/BRL · Margem Operacional/Media Ponderada/% · Inadimplencia > 30d/Fim de Periodo/%
- `metas.versao_meta`: `Orcamento Original` (vigente p/ 2024, 2025; **nao** vigente p/ 2026) · `Revisao 2026` (vigente p/ 2026)

## As sete armadilhas (repetidas aqui porque custam caro)

1. **Cancelamento e point-in-time.** Um titulo cancelado em out/2025 nao pode contar como inadimplente numa foto de dez/2025, mas contava numa foto de set/2025. Ignorar isso infla a inadimplencia de 9,4% para 18,7% em jun/2026. Sempre `data_cancelamento IS NULL OR data_cancelamento > :ref`.
2. **Vencido e calculado, nunca lido.** `status_titulo` e uma foto de 2026-08-31. Para qualquer data de referencia, recalcule.
3. **`eh_versao_vigente`**: 2026 tem duas versoes de orcamento; somar as duas dobra o ano.
4. **Metas percentuais nao se somam.** `tipo_agregacao` manda: margem = media ponderada por Receita Liquida; inadimplencia = valor do ultimo mes do periodo.
5. **Efeito base**: janelas moveis de 12 meses so estabilizam a partir de jan/2025.
6. **Custo de veiculo ocioso nao tem segmento** (`custos.id_contrato IS NULL`), por isso Custo, Margem e Inadimplencia so tem meta no nivel Empresa.
7. **2026 e ano parcial** (8 meses). Comparacao anual sem ajuste de periodo mente.

## Numeros de referencia: o app TEM que reproduzir estes

| Ano | Faturamento bruto | Receita liquida | Custos | Margem |
|---|---|---|---|---|
| 2024 | 29,8 mi | 27,9 mi | 18,3 mi | 34,7% |
| 2025 | 35,0 mi | 32,8 mi | 21,5 mi | 34,5% |
| 2026 (8m) | 24,6 mi | 23,0 mi | 15,6 mi | 32,4% |

Inadimplencia > 30d point-in-time: dez/24 **3,56%** · jun/25 **6,47%** · dez/25 **10,20%** · jun/26 **9,37%**
(numerador = valor_bruto vencido ha >30d, nao pago e nao cancelado *na data ref*;
 denominador = faturamento bruto dos **ultimos 12 meses de competencia**, tambem point-in-time.)

Aging em 2026-08-31 (excl. cancelados e baixados): a vencer 4,47 mi · 1-30d 0,76 mi · 31-60d 0,44 mi ·
61-90d 0,40 mi · 91-180d 0,77 mi · 180+ 0,82 mi.

Realizado x meta vigente: 2024 fat. −2,7% · 2025 fat. +6,8%, **inadimplencia +7,20 p.p.** · 2026(8m) fat. +2,9%.
A historia central do dataset: **faturamento e caixa acima do plano, a crise e de credito**.

## Layout do projeto: fixo, nao mude

```
streamlit_app.py          # entrypoint, st.navigation
frotas/                   # pacote (camada de dados e UI compartilhada)
  config.py               # carregamento de segredos
  db.py                   # engine + cache
  metrics/                # camada semantica (SQL parametrizado)
  ui/                     # tema, formatacao, componentes
views/                    # uma pagina por arquivo, alvo de st.Page
docs/                     # 00 briefing · 01 kpis · 02 arquitetura · 03 ux · 04 handover
.streamlit/config.toml
requirements.txt
README.md
```

Convencoes: codigo e comentarios em **pt-BR**; identificadores sem acento; numeros formatados
em padrao brasileiro (R$ 1.234,56 · 12,3% · p.p.). Nenhum segredo em arquivo versionado.
