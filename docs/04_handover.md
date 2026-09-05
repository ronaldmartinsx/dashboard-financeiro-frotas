# 04 — Handover

Fecha o trabalho da equipe de cinco agentes (KPIs · arquitetura de dados · UX/dataviz ·
front-end · tech lead). Registra o que foi decidido e por quê, o que ficou em aberto,
e o que alguém precisa saber antes de mexer ou publicar.

Estado atual: **5/5 páginas renderizam sem exceção**, `validar_metricas` em **110/110**,
`verificar_rotulos` em **241 rótulos sem nome de coluna exposto**.

---

## 0. Redução de escopo — 2026-09-02

O projeto foi reduzido a **cinco eixos**: Faturamento · Recebimento · **Inadimplência
somente na posição atual** · Metas · Custos. A entrega original tinha 5 páginas
analíticas e 179 verificações; agora são 1 guia + 4 páginas e 110 verificações.

**O que saiu, e por decisão explícita do dono do projeto:**

| Removido | Observação |
|---|---|
| Margem Operacional | por completo — inclusive como linha na tabela de metas, embora exista na tabela `metas` do banco |
| Série retroativa de inadimplência | 32 fotos mensais, heatmap segmento × mês, recuperação por safra |
| Página de Margem e Contratos | margem por contrato, contratos deficitários, margem por tipo e por segmento |
| Análise de frota | corretiva por faixa de idade, corretiva recorrente por veículo, margem por veículo |
| Curva ABC / concentração | substituída por um top 10 de clientes por faturamento |
| Seção de cancelamentos | virou nota de rodapé do visual de faturamento |

**O que foi preservado de propósito**, apesar de parecer ligado ao removido:

- **`inadimplencia_ponto_no_tempo`** — é a foto na data de referência, o coração do eixo 3.
  Some a série; fica a posição atual, para qualquer data que o usuário escolher.
- **A lógica point-in-time de cancelamento dentro do faturamento válido.** A seção saiu da
  tela, mas o cálculo é a armadilha nº 1 do dataset: sem ele a inadimplência infla de
  9,4% para 18,7%.
- **`_cancelamentos_por_motivo`**, tornada privada — é a única fonte do alerta A19, que fica.

**Duas regras editoriais** passaram a valer e o código as sustenta: uma pergunta central
por página declarada no título, e no máximo um bloco curto de texto por página. Os 48
blocos de texto autoral das páginas antigas viraram 4 blocos de corpo, 12 notas de
rodapé de visual e 2 legendas.

**Nomenclatura**: nenhum nome de coluna do banco pode chegar à tela. `frotas/ui/rotulos.py`
traduz 149 colunas e 45 valores de domínio, e `scripts/verificar_rotulos.py` falha o build
se algo escapar — inclusive em título de eixo, legenda, colorbar e anotação de gráfico.

### 0.1 Dívida de camada conhecida

`frotas/metrics/alertas.py` monta **texto de apresentação** (título e detalhe dos alertas)
e por isso importa `frotas.ui.format` — uma inversão de camada. Foi assim que o app passou
a exibir `R$ 1.774 mi` (formato americano) e o nome de coluna `data_baixa` na tela até
2026-09-02. Corrigido nas strings; a correção estrutural é o alerta devolver **valores
estruturados** e a UI formatá-los. Enquanto não for feito, todo texto novo em `alertas.py`
precisa passar por `fmt.` e sair acentuado.

---

## 1. Decisões de arquitetura, e o porquê

### 1.1 A UI não sabe SQL, não sabe limiar, não sabe cor

Três invariantes, cada uma resolvendo um problema concreto:

- **Só `frotas/metrics/` escreve SQL.** Mantém a definição de cada métrica em um lugar
  só e auditável pelo validador. Uma página que montasse o próprio SQL poderia
  silenciosamente perder o filtro point-in-time de cancelamento — o erro que infla a
  inadimplência de 9,4% para 18,7%.
- **A UI não conhece limiar** (`frotas/metrics/alertas.py`). Três das vinte regras têm
  estado — A2 tem janela de 3 meses, A11 exige 2 meses consecutivos saindo de zero,
  A14 exige 3 meses consecutivos de corretiva alta. Avaliar isso em Python significaria
  transportar a série inteira; elas são resolvidas em SQL e devolvem só os infratores.
- **A UI não inventa cor.** Zero hex literal em `views/`; a paleta foi validada por
  script para daltonismo (ΔE 9,2 no tema claro, 9,4 no escuro) e três matizes que ficam
  abaixo de 3:1 têm regra de alívio em `theme.exige_rotulo_direto()`.

### 1.2 Ano parcial: período casado como leitura primária

2026 tem 8 meses. Comparar o realizado contra a meta **anual** produz números que
mudam de sinal: a margem aparece como −0,61 p.p. contra o ano cheio e **+1,70 p.p.**
contra a meta dos mesmos oito meses. A inadimplência aparece como +2,02 p.p. contra a
meta de dezembro e **+1,22 p.p.** contra a meta de agosto.

`metas.comparativo_anual` devolve as duas leituras (`meta_alinhada`, `meta_anual`,
`base_comparacao`) e a UI exibe **a de período casado como primária, sempre rotulada**
("vs. meta jan/2026 a ago/2026"), com a anual como contexto. Nunca um número solto.

Consequência: os números publicados em `DICIONARIO_DADOS.md` para 2026 (−0,61 p.p. e
+2,02 p.p.) são a leitura anual. Ambos continuam disponíveis e verificados; o app
mostra a outra por ser a honesta para período parcial.

### 1.3 Margem por contrato exigia período casado — *removida na redução de escopo*

Registrado porque a armadilha volta se alguém reintroduzir análise por contrato.

Sem restringir o custo às competências faturadas, `CTR0023` saía com −671% de margem:
receita de 3 dias contra o custo cheio de 10 veículos. Com período casado, os contratos
negativos somavam **R$ 14,8 mil** de prejuízo real, não R$ 148,9 mil — uma diferença de
10×, inteiramente artefato de borda. A função devolvia `meses_com_receita` e
`periodo_parcial` para a UI desenhar contrato parcial como marca vazada e excluí-lo de
todo ranking, citando-o no rodapé em vez de escondê-lo.

**Qualquer métrica por entidade com vigência própria** — contrato, veículo, alocação —
precisa do mesmo cuidado: casar o período de receita com o de custo, e marcar quem tem
período parcial em vez de deixá-lo poluir o ranking.

### 1.4 Transporte é o gargalo, não o banco

O pooler entrega ~1.000 linhas/s com 3 colunas e ~**200 linhas/s** com 9-10. Uma grade
veículo × mês de 6.613 linhas levou **34 s no cliente** para uma query que o servidor
resolve em 108 ms. Daí: regras com estado avaliadas em SQL, `serie_vencido_por_cliente`
devolvendo `id_cliente` em vez do cadastro repetido, e `serie_corretiva_por_veiculo`
com `pct_minimo=25` por padrão.

**Regra para quem for estender: nenhuma chamada deve devolver mais de ~1.000 linhas.**

### 1.5 Preservar o dado, sinalizar na UI

Foi pedido que a inadimplência devolvesse `NULL` antes de 31/01/2025 por causa do
efeito base. Isso apagaria **dez/2024 = 3,56%**, que é número de referência e cuja
janela de 12 meses está completa. Em vez disso a função devolve um booleano
`janela_completa`, e a UI acinzenta pela regra editorial. O mesmo princípio vale para
`nivel='indisponivel'`: cinza, **nunca verde** — ausência de regra não é boa notícia.

---

## 2. Divergências em aberto

Nenhuma bloqueia o app. Todas estão marcadas como informativas no validador.

| # | O que se esperava | O que o banco dá | Leitura |
|---|---|---|---|
| D1 | Cancelamentos 4,0 / 6,0 / 2,0% | 3,53 / 6,23 / 1,97% por competência; 1,22 / 5,45 / 5,88% por ano de cancelamento | Nenhuma definição reproduz 4,0% em 2024. Os valores absolutos conferem (R$ 1,051 / 2,182 / 0,486 mi) — é parâmetro do gerador, não métrica reconstituível. **Não publicar 4/6/2 no app.** |
| D2 | A20 = 6 contratos de período parcial | 1 | O `docs/01_kpis.md` se contradiz: a regra de §7.1 acha 1; contando também os 13 sem receita nenhuma daria 14. Nenhuma leitura dá 6. Adotada a de §7.1. |
| D3 | A17 = −10,1 p.p. | −10,05 p.p. | Diferença de apresentação: o −10,1 vem de subtrair valores já arredondados (24,2 − 34,3). |
| D4 | Taxa de recuperação com corte de 90 dias | 78,2% em 93,4 dias | Os 73,6% em 92 dias publicados foram apurados **sem** o corte. Implementado como parâmetro `dias_maturidade`, padrão 0. |

### Inconsistências internas do dataset (registradas, não corrigidas)

- **4 títulos (R$ 182 mil) têm `data_baixa` posterior à data de extração.** O aging os
  exclui; a inadimplência não. Diferença de R$ 328 mil. Está exposto como alerta A18.
- Títulos baixados entram na inadimplência mas não no aging — decisão de definição,
  documentada em `docs/02_arquitetura.md` §5.

---

## 3. Segurança — um achado corrigido, um pendente

Estado em 2026-09-02. O achado 3.2 foi **aplicado e verificado**; o 3.1 **não**, por
falta de permissão para `CREATE ROLE` no ambiente de execução.

### 3.1 O DSN do app ignora RLS — **PENDENTE**

`PG_DSN` conecta como `postgres`, que tem `rolbypassrls = true`. O caminho Postgres do
app **ignora as policies de RLS**; hoje o único freio de escrita é a sessão read-only
mais a guarda de SQL da camada de dados. Correto é um papel dedicado:

```sql
create role app_leitura login password '...' nobypassrls;
grant usage on schema public to app_leitura;
grant select on all tables in schema public to app_leitura;
alter default privileges in schema public grant select on tables to app_leitura;
alter role app_leitura set default_transaction_read_only = on;
alter role app_leitura set statement_timeout = '30s';
```

Depois, trocar o segredo `PG_DSN` para esse papel — o usuário no pooler é
`app_leitura.<project-ref>`.

**Por que não foi aplicado.** `CREATE ROLE ... LOGIN` é operação privilegiada e foi
bloqueada pela política de permissões do ambiente de execução. Além disso, criá-lo
exigiria gerar uma senha nova, que passaria pelo transcript da sessão — exatamente o
problema de higiene que o §3.3 registra. Definir a senha no seu próprio terminal evita isso.

**Armadilha ao aplicar:** `app_leitura` é `nobypassrls` e as policies existentes valem
para `anon` e `authenticated`. Sem policy própria o papel lê **zero linhas**. O DDL acima
precisa vir acompanhado de:

```sql
do $$
declare t text;
begin
  foreach t in array array['alocacoes_veiculo','calendario','clientes','contratos',
                           'custos','metas','titulos_receber','veiculos']
  loop
    execute format('create policy %I on public.%I for select to app_leitura using (true)',
                   'leitura app_leitura', t);
  end loop;
end $$;
```

Teste depois de trocar o `PG_DSN`: `python3 scripts/validar_metricas.py`. Se as policies
faltarem ele falha em massa (zero linhas), que é exatamente o sintoma a procurar.

### 3.2 Grants de escrita amplos em `public` — **CORRIGIDO em 2026-09-02**

`anon` e `authenticated` tinham `INSERT/UPDATE/DELETE/TRUNCATE` no grant de tabela — só a
ausência de policy de escrita os bloqueava. Um `alter table ... disable row level security`
ou uma policy permissiva acidental abriria escrita imediatamente.

Aplicado pela migration `revogar_escrita_anon_authenticated`:

```sql
revoke insert, update, delete, truncate, references, trigger
  on all tables in schema public from anon, authenticated;

alter default privileges in schema public
  revoke insert, update, delete, truncate, references, trigger on tables
  from anon, authenticated;
```

Verificado: `anon` e `authenticated` têm agora **apenas `SELECT`** em `public`.
`service_role` mantém todos os privilégios, o que é correto — é a chave de backend.

**Resíduo conhecido.** O `alter default privileges` só alcança os defaults do papel que o
executa (`postgres`), dono das 8 tabelas deste projeto. O Supabase mantém um conjunto
próprio sob `supabase_admin` que ainda concede `arwdDxtm` a `anon`/`authenticated` — uma
tabela futura criada **por `supabase_admin`** nasceria com escrita liberada. É
configuração de plataforma e alterá-la exige privilégio que o `postgres` não tem.
Se criar tabelas novas em `public`, confira o grant delas.

### 3.3 Antes de publicar

- A senha do banco circulou em transcript de sessão — **rotacionar** em
  Project Settings → Database se o transcript for compartilhado.
- `git log -p | grep -iE 'postgresql://|service_role|eyJ'` deve voltar vazio.
- A policy de leitura é `qual = true`: qualquer portador da chave publicável lê todos os
  clientes, contratos e títulos. Aceitável para dado sintético; para dado real, exige
  predicado por tenant.

---

## 4. O que ficou fora do escopo

- **Autenticação de usuário.** O app não tem login; qualquer um que alcance a URL vê tudo.
- **Escrita de qualquer natureza** — sem anotações, sem marcação de título como
  "em negociação", sem exportação que persista estado.
- **Modelo preditivo.** Deliberado: os dados são sintéticos e as correlações foram
  programadas. Um modelo treinado aqui aprende as regras do gerador, não comportamento
  de cliente.
- **Testes automatizados de UI.** A verificação de entrega usou `streamlit.testing.v1`
  ad-hoc (ver §5), não uma suíte versionada.
- **Deploy.** Nada foi publicado; não há Dockerfile nem configuração de host.

---

## 5. Como verificar que continua funcionando

O `AppTest.switch_page()` **não funciona** com `st.navigation` — ele renderiza sempre a
página inicial, o que faz um teste ingênuo passar cinco vezes na mesma página. Rode cada
view diretamente:

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("views/pagina_3_inadimplencia.py", default_timeout=400)
at.run()
assert not at.exception and not at.error
```

`views/_comum.contexto()` cai para `Filtros()` padrão quando não há `session_state`, então
a view roda isolada. Para testar outro recorte, injete antes do `run()`:

```python
at.session_state["filtros"] = Filtros.criar(
    competencia_ini=date(2025,1,1), competencia_fim=date(2025,12,1), data_ref=date(2025,12,31))
```

Rode também `python3 scripts/verificar_rotulos.py`: ele instrumenta `st.plotly_chart` e
`st.dataframe` e falha se um nome de coluna do banco chegar à tela. Foi provado que ele
falha de verdade — uma página-canário com `valor_bruto` de cabeçalho, `inadimplencia_pct`
de eixo e `realizado` de série foi pega nos três casos.

Tempo de carga com cache frio: página de metas **~8,5 s** (a mais pesada), guia **0,2 s**
(não consulta o banco de propósito — é a página que sobrevive ao banco fora do ar), demais
entre 2,2 s e 3,1 s.

---

## 6. Próximos passos, em ordem de valor

1. **Criar o papel `app_leitura`** (§3.1, junto com as policies que ele exige) e
   rotacionar a senha do `postgres` no dashboard. O revoke de escrita (§3.2) já foi
   aplicado em 2026-09-02. É o que falta para publicar.
2. **Alertas devolverem valores estruturados** em vez de texto pronto (§0.1). É a dívida
   de camada que já produziu formatação americana e nome de coluna na tela.
3. **Nenhum alerta roteado para a página 2** (faturamento e recebimento). A eficiência de
   cobrança (A4) vive na página de metas; se a página de recebimento deve ter alerta
   próprio, é uma decisão de roteamento a tomar.
4. **Fechar D1 com quem gerou o dataset** — ou remover 4/6/2% de qualquer material que
   cite esses números como referência.
5. **Suíte de teste versionada** a partir do harness de §5, ligando `validar_metricas` e
   `verificar_rotulos`.
6. **Autenticação**, se o app sair de uso interno.
