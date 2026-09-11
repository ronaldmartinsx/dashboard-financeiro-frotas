# Contexto para agentes de código

Dashboard financeiro de uma locadora de frotas B2B. Streamlit sobre um snapshot Parquet
local, com a regra de negócio numa camada semântica testada. Dataset sintético.

Este arquivo é a instrução que você recebe antes de encostar em qualquer coisa. Para o
raciocínio por trás de cada decisão, veja [`docs/`](docs/).

## Antes de commitar, sempre

```bash
python3 scripts/verificar_tudo.py
```

Seis portões em 3,5 s. Só devolve 0 se todos passarem, e o mesmo comando roda no GitHub
Actions a cada push. Nunca proponha um commit sem ter rodado.

Rodar o app: `streamlit run streamlit_app.py`. Não precisa de credencial.

## As camadas, e a direção em que elas conversam

```
views/  ->  frotas.metrics.*  ->  frotas.db.consultar  ->  DuckDB sobre dados/*.parquet
```

A seta não tem volta. `views/` consome `frotas.metrics` e `frotas.filtros`, e nada mais.

## Invariantes que não se negociam

Cada uma destas é verificada por script, não combinada. Quebrar qualquer uma reprova a
suíte:

- **Só `frotas/metrics/` escreve SQL.** `views/` e `frotas/ui/` não abrem conexão.
- **A UI não conhece limiar.** Nível e cor de alerta vêm de `frotas.metrics.alertas`.
- **A UI não inventa cor.** Zero hexadecimal literal fora de `frotas/ui/theme.py`.
- **Todo número passa por `frotas.ui.format`**, inclusive os separadores do Plotly.
- **Nenhum nome de coluna do banco chega à tela.** Tudo passa por `frotas.ui.rotulos`.
- **Nenhum número sem procedência chega à tela**, inclusive os de texto gerado por
  modelo, conferidos um a um em `frotas/leitura.py`.

## Vocabulário na tela

O público é gestor de negócio, não técnico. Na tela e na documentação pública:

- Português com acento. Nada de `snake_case`, nada de abreviação obscura.
- Vocabulário de negócio, nunca técnico. Sem "dataframe", "flag", "limiar", "nível
  vermelho", "point-in-time".
- **Sem travessão em prosa.** Vale para a tela, para este arquivo, para o README e para
  `docs/`. O `—` sozinho em célula de tabela é o vazio do `format.VAZIO` e pode ficar.
- Nunca dois `$` na mesma string: o Markdown do Streamlit interpreta como LaTeX.

Regras editoriais das páginas: **uma pergunta central por página, declarada no título**, e
**no máximo um bloco curto de texto por página**. Banner de alerta sempre depois dos
números grandes, nunca antes.

## Armadilhas do dataset

Três erros que já custaram caro e que qualquer métrica nova precisa respeitar:

1. **Corte point-in-time de cancelamento.** Um título cancelado hoje não pode ser
   inadimplente numa foto de antes do cancelamento. Sem esse corte a inadimplência sai
   18,7% em vez de 9,4%.
2. **Meta por período casado.** 2026 tem 8 meses realizados. Comparar contra o orçamento
   do ano cheio dá −31% de faturamento, que é calendário e não performance.
3. **`eh_versao_vigente` nas metas.** 2026 tem duas versões de orçamento. Somar as duas
   dobra o ano.

Ver `DICIONARIO_DADOS.md` para a lista completa.

## O que nunca fazer

- **Nenhuma escrita.** Sem `INSERT`, `UPDATE`, `DELETE` ou DDL em código do app. A guarda
  de `frotas/db.py` recusa qualquer SQL que não comece por `SELECT` ou `WITH`.
- **Nunca imprimir, logar ou escrever valor de segredo.** Mensagens de erro citam a
  origem esperada, jamais o valor. `.env` e `.streamlit/secrets.toml` são ignorados pelo
  git e ficam assim.
- **Não colorir o número grande do tile** nem a nota de armadilha. Cor pertence ao dado.
- **Não adicionar cor fora de `theme.py`**, nem reordenar a paleta: a ordem é escada de
  luminância e a separação em daltonismo é medida.
- **Não somar métrica percentual.** Inadimplência é fim de período, nunca soma de meses.

## Quando um defeito escapar para a tela

Corrigir não basta. **Todo portão desta suíte nasceu de um defeito que passou**, e o
portão só entra depois de ser provado: reintroduza o defeito, confirme que o portão
reprova, e só então confie nele. Portão que nunca falhou não é portão.

## Fluxo de trabalho

A `main` é protegida. Mudança entra por branch e pull request, com a verificação verde.

```bash
git checkout -b tipo/assunto-curto
# ... mudança ...
python3 scripts/verificar_tudo.py
git commit
git push -u origin tipo/assunto-curto
gh pr create
```

Commits em português, explicando **por que**, não o que o diff já mostra.

## Decisões que são do dono do projeto, não suas

Escopo, vocabulário de tela, prioridade e qualquer coisa que mude o que o usuário lê.
Proponha, argumente, mas não decida sozinho. Decisões revertidas estão registradas em
`docs/04_handover.md` e continuam valendo como revertidas.
