# Dashboard Financeiro — Streamlit + Supabase

Dashboard financeiro de uma locadora de frotas B2B. Lê o dataset direto do
Supabase (Postgres, **somente leitura**) e responde quatro perguntas de negócio, uma por
página, mais um guia de abertura.

A leitura que o app existe para permitir: **faturamento e caixa estão acima da meta;
a crise é de crédito, não de receita.** A inadimplência > 30d fecha 2025 em 10,20%
contra uma meta de 3,00% — um desvio de +7,20 p.p., o maior do dataset.

## Rodando

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Credenciais

O app precisa de `PG_DSN` (Postgres via pooler do Supabase). A precedência é:

1. `st.secrets` — `.streamlit/secrets.toml`, para deploy;
2. variável de ambiente `PG_DSN`;
3. `.env` na raiz, para desenvolvimento local.

Nenhum dos três vai para o repositório: `.env` e `.streamlit/secrets.toml` estão no
`.gitignore`. O app nunca imprime o valor de um segredo — em caso de erro reporta apenas
a origem consultada. Sem credencial, sobe com uma tela de instruções em vez de stack trace.

## Escopo — cinco eixos

Faturamento · Recebimento · **Inadimplência na posição atual** · Metas · Custos.

Fora de escopo por decisão de projeto: margem operacional, análise de contratos,
concentração de carteira, recuperação de crédito e toda série retroativa de
inadimplência. A inadimplência é uma **foto na data de referência**, nunca uma série.

## Guia e quatro páginas

O menu lateral leva o **nome curto**; a **pergunta de negócio** é o título dentro da página.

| Menu | Pergunta central (título da página) | Público |
|---|---|---|
| Guia | Como ler este dashboard? | quem abre pela primeira vez |
| Metas | Estamos entregando a meta? | CFO |
| Faturamento e Recebimento | Quanto faturamos e quanto entrou em caixa? | Controller / CFO |
| Inadimplência | Quanto está em aberto hoje, e com quem? | Gerente de crédito e cobrança |
| Custos | Para onde vai o custo? | Gerente de operação e frota |

Toda página abre com o mesmo cabeçalho: **Dashboard Financeiro · <seção>**, a pergunta
de negócio como título, e os **chips de contexto**, que repetem os filtros em uso. Os chips
ficam no topo, e não num rodapé, porque contexto de apuração se lê antes do número, e porque
o recorte só existia na barra lateral, invisível com ela recolhida.

**Cada página exibe apenas os filtros que mudam os números dela** (`FILTROS_DA_PAGINA` em
`views/_comum.py`, derivado de `filtros.politica_filtros()`). Metas troca o período por um
seletor de **exercício**, porque tudo ali é por ano, e não lista porte, rating, tipo de
contrato nem cliente, porque o orçamento só existe nos níveis Empresa e Segmento;
Inadimplência não lista período, porque a página é uma leitura numa data; Custos não lista
data, porque seus números são todos por competência. Filtro visível que
não faz nada é pior que filtro nenhum: o usuário mexe e conclui que o dashboard quebrou.

**Granularidade do eixo temporal**: as páginas com série (Metas, Faturamento e Recebimento,
Custos) trazem **Agrupar o tempo por** — mês, trimestre ou ano. Cada coluna declara como se
agrega (`reagrupar()` em `views/_comum.py`): reais somam, a inadimplência é fim de período
(o trimestre é o valor do último mês, nunca a soma dos três) e a ociosidade é recalculada
como veículos-mês parados sobre veículos-mês de frota. **Semana não existe** e não é
omissão: `titulos_receber.competencia` e `custos.competencia` são sempre dia 1 do mês, e a
meta é mensal por definição. Só `data_pagamento` tem grão diário.

Duas regras editoriais que o código sustenta: **uma pergunta central por página,
declarada no título**, e **no máximo um bloco curto de texto por página** — o resto é
rótulo, nota de rodapé do visual ou tooltip.

## Estrutura

```
streamlit_app.py          entrypoint: st.navigation, filtros globais, estado compartilhado
frotas/
  config.py               segredos (st.secrets > env > .env) e constantes de negócio
  db.py                   engine, cache, guarda SELECT/WITH, erros tipados
  filtros.py              dataclass Filtros (frozen/hashável) + política de filtros
  metrics/                camada semântica — a única que escreve SQL
    receita.py  credito.py  custos.py  metas.py  alertas.py  dimensoes.py
  ui/
    theme.py              tokens de cor, paletas validadas para daltonismo, layout Plotly
    format.py             formatação pt-BR (R$, %, p.p., competência, delta)
    rotulos.py            dicionário único coluna → rótulo legível (149 colunas)
    componentes.py        tiles, banners, tabelas, seletores
views/                    guia + uma página por pergunta, mais _comum.py
scripts/
  verificar_tudo.py       roda as quatro verificações; use antes de commitar
  validar_metricas.py     110 verificações contra os números publicados
  verificar_rotulos.py    falha se nome de coluna, travessão ou cifrão cru chegar à tela
docs/                     00 briefing · 01 KPIs · 02 arquitetura · 03 UX · 04 handover
```

## Validação

```bash
python3 scripts/verificar_tudo.py
```

Roda tudo de uma vez e só devolve 0 se as quatro passarem: `pyflakes`, as métricas,
os rótulos e o render das cinco páginas. **Chame antes de commitar.**

```bash
python3 scripts/validar_metricas.py
```

Roda a camada semântica contra o banco e compara com os números de referência de
`DICIONARIO_DADOS.md`. Saída esperada: **110/110 obrigatórias OK**, 3 informativas
(divergências de definição documentadas em `docs/04_handover.md`).

Cobre, entre outros: faturamento, receita líquida e custos dos três anos; inadimplência
na data de referência em quatro pontos; aging casa a casa; realizado × meta de
faturamento e recebimento; e o nível esperado dos 13 alertas.

```bash
python3 scripts/verificar_rotulos.py
```

Renderiza todas as páginas e **falha se qualquer nome de coluna do banco chegar à tela** —
cabeçalho de tabela, título de eixo, legenda, colorbar, anotação, rótulo de widget e o
**texto livre** de `st.caption`, `st.markdown` e `st.expander`. Na prosa ele também pega
travessão em texto corrido e cifrão cru (dois `$` na mesma string viram LaTeX no Streamlit)
— os dois defeitos que já escaparam para a tela.

## Regras de arquitetura

Cinco invariantes que a revisão verifica e que devem continuar valendo:

- **Só `frotas/metrics/` escreve SQL.** `views/` e `frotas/ui/` não abrem conexão.
- **A UI não conhece limiar.** Nível e cor de alerta vêm de `frotas.metrics.alertas`.
- **A UI não inventa cor.** Zero hex literal em `views/` — tudo vem de `frotas.ui.theme`.
- **Todo número passa por `frotas.ui.format`**, inclusive os separadores do Plotly.
- **Nenhum nome de coluna do banco chega à tela** — tudo passa por `frotas.ui.rotulos`.

## Segurança

O app é read-only em profundidade: sessão Postgres em `default_transaction_read_only`,
guarda que rejeita qualquer SQL que não comece por `SELECT`/`WITH`, e SQL sempre
parametrizado. Nenhuma operação de escrita existe no código.

Da auditoria da camada de dados saíram dois achados:

- **Corrigido em 2026-09-02** — `anon` e `authenticated` tinham grants de
  `INSERT/UPDATE/DELETE/TRUNCATE` em `public`, bloqueados apenas pela ausência de
  policy de escrita. Agora têm somente `SELECT`.
- **Pendente** — o `PG_DSN` conecta como `postgres`, que tem `rolbypassrls = true`:
  o app ignora as policies de RLS. O papel dedicado `app_leitura`, as policies que ele
  exige e o teste de verificação estão em `docs/04_handover.md` §3.1.
  **Aplique antes de publicar.**

## Ressalva sobre os dados

Dataset 100% sintético, com narrativas plantadas e período de competência de
jan/2024 a ago/2026. Não representa nenhuma empresa real e não serve para benchmark.
2026 é ano parcial (8 meses) — toda comparação contra meta usa período casado.
