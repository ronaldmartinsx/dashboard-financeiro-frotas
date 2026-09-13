# 05 A solução explicada

Este documento existe para uma coisa: permitir defender cada decisão deste projeto sem
consultar o código. Ele responde o que a solução resolve, como cada número é calculado, a
que conclusão os dados levaram, como a IA entra e como ela é impedida de inventar número.

Os outros documentos de `docs/` explicam o raciocínio de cada camada em profundidade. Este
amarra tudo.

---

## 1. O problema

Uma locadora de frotas B2B fatura por contrato mensal, recebe com atraso e opera uma frota
que custa dinheiro mesmo parada. O financeiro dessa empresa precisa responder quatro
perguntas toda semana, e as respostas moram em lugares diferentes:

1. Estamos entregando a meta?
2. Quanto faturamos e quanto realmente entrou em caixa?
3. Quanto está em aberto hoje, e com quem?
4. Para onde vai o custo?

O que normalmente acontece é um painel com trinta indicadores em que nenhuma dessas
perguntas tem dono. A pessoa olha, entende que "está tudo mais ou menos", e decide por
intuição.

**A decisão de produto deste projeto foi inverter isso: uma pergunta por tela, declarada no
título da própria tela.** Cinco páginas, cinco perguntas. Se um número não ajuda a
responder a pergunta da página em que está, ele não pertence àquela página.

### Por que isso é uma decisão e não um capricho

Porque tem custo. Métricas que seriam úteis ficaram de fora: margem por contrato saiu da
primeira versão, análise de recuperação de crédito saiu, série retroativa de inadimplência
saiu. Escopo é decisão de risco, não preguiça: cada item a mais é uma superfície a mais
para o número estar errado sem ninguém perceber.

---

## 2. A conclusão a que os dados levaram

**A tese não veio de briefing. Veio dos números, e contraria o que se esperaria.**

| Exercício | Faturamento | Recebimento | Custo | Inadimplência acima de 30 dias |
|---|---|---|---|---|
| 2024 | −2,7% | −4,7% | −2,1% | 3,56% *(meta 3,00%)* |
| 2025 | **+6,8%** | −2,9% | **+8,2%** | **10,20%** *(meta 3,00%)* |
| 2026 *(8 meses)* | +2,9% | +3,6% | +0,3% | 10,02% *(meta 8,00%)* |

Em 2025 a empresa **bateu a meta de faturamento estourando a de custo**, e o caixa fechou
abaixo do plano no mesmo ano em que a receita ficou acima. É a assinatura clássica de
crescimento financiado por prazo: vende mais, entrega mais, e recebe pior.

O desvio de **+7,20 pontos percentuais** na inadimplência de 2025 é o maior do conjunto de
dados por uma ordem de grandeza. O orçamento de 2026 reconheceu a realidade e revisou a
meta de 3,00% para 8,00%. Ainda assim o realizado está em 10,02%.

**A frase que resume:** faturamento e caixa estão acima da meta. A crise é de crédito, não
de receita.

### Três achados que não estavam na pergunta original

**O rating de crédito funciona, e ninguém está usando.** Um cliente com rating D tem 16,94%
do próprio faturamento vencido, contra 0,67% de um cliente A: erra 25 vezes mais. Mas os
clientes C têm o **maior limite médio da base**, 50% acima dos A. Há **R$ 1,33 mi em aberto
acima dos limites aprovados**, concentrados em 13 de 49 clientes. O modelo de risco existe
e classifica bem; a política de limite simplesmente não olha para ele.

**Os veículos parados não estão esperando cliente, estão quebrados.** 40,5% do custo de
veículo sem contrato é manutenção e pneu. A leitura natural de ociosidade é comercial (não
vendemos o suficiente). O dado diz que é oficina.

**A empresa gasta 3,7 vezes mais consertando do que prevenindo:** R$ 8,00 mi de manutenção
corretiva contra R$ 2,16 mi de preventiva. É a decisão isolada mais cara do painel de
custos, e não foi decidida por ninguém. Foi tomada por omissão.

---

## 3. As cinco telas, e o que cada uma decide

| Tela | Pergunta no título | Quem usa | Que decisão sustenta |
|---|---|---|---|
| Guia | Como ler este dashboard? | quem abre pela primeira vez | nenhuma; evita a leitura errada |
| Metas | Estamos entregando a meta? | CFO | onde intervir no trimestre |
| Faturamento e Recebimento | Quanto faturamos e quanto entrou em caixa? | Controller | se o problema é venda ou cobrança |
| Inadimplência | Quanto está em aberto hoje, e com quem? | crédito e cobrança | quem ligar hoje, quem bloquear |
| Custos | Para onde vai o custo? | operação e frota | onde cortar sem derrubar entrega |

**A ordem não é alfabética nem cronológica, é de afunilamento.** Metas diz que existe um
problema de crédito. Inadimplência diz que segmento e que ratings. A fila de cobrança da
mesma página diz quais clientes, e qual título. Três cliques da manchete até a linha de
cobrança.

### O cabeçalho é idêntico nas cinco

Nome da seção, a pergunta de negócio como título, e os chips de contexto repetindo os
filtros em uso. Os chips ficam no topo e não no rodapé porque **contexto de apuração se lê
antes do número, não depois**. Com a barra lateral recolhida, o recorte deixaria de existir
na tela.

### Cada página só mostra os filtros que mudam os números dela

Metas troca período por **exercício**, porque tudo ali é anual, e não lista porte, rating
nem cliente, porque o orçamento só existe nos níveis Empresa e Segmento. Inadimplência não
lista período, porque é uma leitura numa data. Custos não lista data, porque seus números
são todos por competência.

**Filtro visível que não faz nada é pior que filtro nenhum:** a pessoa mexe, o número não
muda, e ela conclui que o dashboard quebrou.

---

## 4. Como cada número é calculado

### Faturamento bruto e faturamento válido

Bruto é a soma de tudo que foi emitido. **Válido exclui os títulos cancelados na data de
referência.** A diferença entre os dois é a taxa de cancelamento, que fica na nota de
rodapé do visual e é a porta de entrada da armadilha 1 mais abaixo.

### Receita líquida

`valor_liquido` somado, ou seja, bruto menos impostos. É o denominador da margem.

### Recebimento em caixa

Soma do que foi efetivamente pago, **por data de pagamento e sem juros e multa**. Dois
detalhes que importam:

- **Por data de pagamento, não por competência.** Recebimento de um mês não casa com o
  faturamento do mesmo mês, e não deve casar: o descasamento entre faturar e receber é de 1
  a 3 meses, e é justamente o que o indicador existe para mostrar.
- **Sem juros e multa.** Juros não é receita de locação, é penalidade. Incluir inflaria o
  numerador de um indicador de cobrança justamente quando a cobrança vai mal.

### Cobertura de caixa

```
recebido nos últimos 12 meses  ÷  faturado válido das mesmas 12 competências
```

Na data de referência: 32,49 mi ÷ 35,12 mi = **92,5%**. Lê-se: de cada R$ 100 faturados nos
últimos doze meses, R$ 92,50 entraram.

**Por que doze meses e não o mês:** num único mês o indicador mediria descasamento de prazo,
não cobrança. A janela de doze meses neutraliza o prazo e deixa só a eficiência.

### Inadimplência acima de 30 dias, a métrica central

```
numerador   = valor bruto de títulos vencidos há mais de 30 dias,
              não pagos e não cancelados NA DATA DE REFERÊNCIA
denominador = faturamento bruto dos últimos 12 meses de competência,
              também com filtro point-in-time de cancelamento
```

Três coisas que ela **não** é, e que são os erros comuns:

- Não é sobre a carteira vencida (vencido dividido por carteira em aberto).
- Não é sobre o faturamento acumulado do ano.
- Não é uma série histórica. É uma **foto numa data**, e cada ponto de uma série exigiria
  recalcular a foto inteira naquele dia.

**Os 30 dias são carência**, não atraso: uma fatura vencida ontem é atraso operacional, não
inadimplência.

### Realizado contra meta

A regra única do projeto: **compara-se sempre com a meta dos mesmos meses**, nunca com o
orçamento do ano cheio. Ver armadilha 2.

### Ociosidade

Veículos sem contrato no mês, sobre a frota com custo no mesmo mês. E o **custo de
ociosidade** é o custo desses veículos, que existe mesmo sem receita associada.

Ao mudar a granularidade do eixo de tempo, ociosidade **é recalculada** como veículos-mês
parados sobre veículos-mês de frota. Não é a média das taxas mensais, porque taxa não se
soma nem se tira média simples.

---

## 5. As três armadilhas do dado

São os três erros que fariam o painel mentir com convicção. Estão no `CLAUDE.md` porque
qualquer métrica nova precisa respeitá-los.

### 1. Corte point-in-time de cancelamento

Um título cancelado em out/2025 **não pode** aparecer como inadimplente numa foto de
dez/2025. Mas **estava** em aberto numa foto de set/2025, e ali conta.

A implementação é uma condição em toda consulta que olha o passado:

```sql
data_cancelamento is null or data_cancelamento > :ref
```

**Sem esse corte, a inadimplência sai 18,7% em vez de 9,4%.** O dobro. Aplicar o status
atual sobre a série inteira é o comportamento padrão de quase toda ferramenta de BI, porque
é o que uma tabela de fatos "limpa" naturalmente produz.

### 2. Meta por período casado

2026 tem oito meses realizados. Comparar com o orçamento do ano cheio dá **−31% de
faturamento**. Comparar com a soma das metas dos mesmos oito meses dá **+2,9%**.

A diferença entre "estamos afundando" e "estamos acima da meta" era calendário, não
performance. O painel soma as metas dos meses correspondentes e **escreve isso na tela**,
numa nota, para ninguém precisar confiar.

### 3. Duas versões de orçamento

2026 tem duas versões de meta, e somar as duas dobra o ano. Só a versão vigente conta. A
revisão cortou o faturamento planejado de 37,80 mi para 35,82 mi e subiu a meta de
inadimplência de 6,50% para 8,00%.

Esse detalhe também é a prova de que o orçamento não conhece o futuro: cada versão foi
montada sobre o realizado do ano anterior.

---

## 6. Os alertas

**13 regras** avaliadas a cada carregamento, distribuídas em quatro categorias: empresa,
crédito, frota e qualidade de dado. Só o que estoura vira banner na tela, com o valor, a
gravidade e o link para a página que explica.

| Regra | O que vigia | Âmbar | Vermelho |
|---|---|---|---|
| A1 | Inadimplência acima da meta do mês | +1,0 p.p. | +2,0 p.p. |
| A3 | Faturamento abaixo da meta | 95% da meta | 90% |
| A4 | Cobertura de caixa | 95% | 93% |
| A6 | Custo acima da meta do mês | 105% da meta | 110% |
| A7 | Cliente com vencido alto sobre a própria receita | 10% | 20% |
| A8 | Cliente acima do limite de crédito | 80% do limite | 100% |
| A9 | Segmento com inadimplência desproporcional | 1,5x a empresa | 2,0x |
| A10 | Vencido há mais de 180 dias, por cliente | qualquer valor | R$ 100 mil |
| A12 | Títulos com mais de 300 dias, a caminho da baixa | | qualquer ocorrência |
| A15 | Taxa de ociosidade da frota no mês | 4% | 6% |
| A16 | Peso do custo de ociosidade em 12 meses | 2,5% | 4,0% |
| A18 | Baixa posterior à data de referência | qualquer ocorrência | |
| A19 | Cancelamento por falha de processo | 1% do faturamento | 3% |

**Duas decisões de desenho valem ser defendidas:**

**A UI não conhece limiar.** Nível e cor vêm da camada de métricas. A tela não sabe o que é
"ruim", ela recebe o nível pronto. Isso impede que a mesma regra tenha dois valores em duas
páginas.

**O banner vem depois dos números grandes, nunca antes.** Um alerta antes do número tira do
leitor a chance de formar a própria leitura. Ele lê o número, forma uma impressão, e então o
sistema diz o que ele deveria notar.

**A18 e A19 são alertas sobre o próprio dado**, não sobre o negócio. Um título com baixa
registrada depois da foto significa que a foto foi tirada errada. Um painel que não vigia a
própria fonte está apenas exibindo com confiança o que recebeu.

---

## 7. A arquitetura

```
views/  ->  frotas.metrics.*  ->  frotas.db.consultar  ->  DuckDB sobre dados/*.parquet
```

Uma direção só, sem volta. As telas consomem `frotas.metrics` e `frotas.filtros`, e nada
mais. Não abrem conexão, não escrevem SQL, não conhecem nome de coluna.

### Os dados viajam com o projeto

O app **não conecta em banco nenhum**. Lê oito arquivos Parquet que somam **459 KB**,
versionados no repositório, consultados pelo DuckDB dentro do próprio processo. Não há
servidor, não há rede e não há credencial: `git clone`, `pip install`, e roda.

Não foi assim desde o começo. O projeto consultava um Postgres gerenciado ao vivo. A troca
foi deliberada, e o ganho está medido:

| | Postgres gerenciado | Snapshot local |
|---|---|---|
| Metas, a página mais pesada | ~12 s | **0,33 s** |
| Demais páginas | ~2 s | **0,06 a 0,08 s** |
| Suíte de verificação completa | ~82 s | **3,5 s** |

### Por que DuckDB e não pandas

Essa é a pergunta técnica mais provável, e a resposta é sobre risco, não sobre velocidade.

A camada semântica inteira é SQL, e é dentro dela que moram as três armadilhas. Reescrever
em pandas jogaria fora **as 116 verificações que validam exatamente aquele SQL**. Com
DuckDB, o texto das consultas continuou o mesmo que rodava no Postgres.

Duas diferenças de dialeto tiveram que ser resolvidas de forma portável, e uma função foi
recriada como macro. Nenhuma consulta precisou ser tocada.

### O que a arquitetura custa

Ela é honesta sobre os limites: **um snapshot não atualiza**. Regenerar exige rodar o
exportador contra a origem. Para um painel de fechamento mensal isso é adequado; para um
painel operacional que precisa do dado de hoje, não seria. A escolha casa com a natureza da
pergunta, e não com uma preferência técnica.

---

## 8. A IA na solução

### O que ela faz, exatamente

A página de Metas tem um bloco **"O que estes números estão dizendo?"** com um botão. Ao
clicar, a API do Claude escreve a leitura do exercício em três parágrafos: o que vai bem, o
que preocupa, e a ação mais urgente.

**Modelo:** `claude-opus-5`, com pensamento adaptativo ligado.
**Teto de saída:** 8.000 tokens.
**Custo:** o payload tem cerca de 1.500 tokens e a resposta cerca de 400. Alguns centavos
por leitura, sob demanda, nunca no carregamento da página, e o resultado fica em cache por
payload.

### O que ela não faz, e essa é a parte importante

**O modelo não tem acesso a dado nenhum.** Não vê SQL, não vê os arquivos, não consulta e
não calcula. Ele recebe um **dicionário de números que a camada de métricas já apurou**, os
mesmos que as 116 verificações cobrem. O trabalho dele é um só: interpretar e priorizar.

O payload é montado com **rótulos de negócio, não nomes de coluna**:

```json
{
  "contexto": { "exercicio": 2026, "data_da_leitura": "31/08/2026" },
  "constantes_do_negocio": {
    "dias_para_a_fatura_virar_inadimplencia": 30,
    "meses_da_janela_da_inadimplencia": 12,
    "dias_para_a_fatura_ser_baixada": 365
  },
  "caixa": {
    "recebido_em_12_meses_reais": 32491234.0,
    "cobertura_de_caixa_pct": 92.51
  },
  "realizado_contra_meta": [ ... ],
  "alertas_ativos": [ ... ]
}
```

A razão de os rótulos serem de negócio é direta: **o modelo escreve o que lê.** Um payload
com `pct_vencido_30d` acabaria com `pct_vencido_30d` na tela do CFO.

### Todo número do payload é arredondado em duas casas

Não é cosmético. Um payload com `2.8411` produzia `"2,8411%"` no texto. **A forma de
impedir precisão falsa no texto é não ter precisão falsa no payload.**

### As instruções ao modelo

O prompt de sistema é explícito sobre a proibição central:

> REGRA ABSOLUTA: use somente números que estão no JSON. Não some, não divida, não estime,
> não converta unidade, não arredonde para uma casa que o JSON não tem. Se uma afirmação
> exigir um número que não está lá, escreva a afirmação sem o número ou não a escreva. Uma
> resposta com um número que não veio do JSON é descartada inteira por um verificador
> automático.

E sobre a forma: três parágrafos de no máximo quatro linhas, no máximo três números por
parágrafo, valores em reais na forma compacta, português de negócio, sem jargão, sem
travessão.

**Mas a instrução não é a garantia.** A instrução é o pedido. A garantia é a seção
seguinte.

---

## 9. Como garantimos que a IA não invente número

Esta é a pergunta que mais vale saber responder, porque é onde quase toda solução com LLM
para de explicar.

### O princípio

> O modelo de linguagem decide o que dizer. O código decide o que pode ser feito.

Prompt não é controle. Prompt é pedido educado. O controle é o código que roda depois.

### O mecanismo, passo a passo

**1. Extrai todo token numérico do texto gerado.** Uma expressão regular reconhece número em
português do Brasil, com prefixo e unidade opcionais: `R$ 3,52 mi`, `92,5%`, `+7,20 p.p.`,
`1.089`, `44`.

**2. Tira as datas antes.** `31/08/2026` viraria três números sem procedência. Datas saem da
varredura porque os pedaços delas não são números de negócio.

**3. Monta o conjunto de números permitidos**, percorrendo o payload em qualquer
profundidade. **Inclusive dentro de texto:** a faixa se chama "Mais de 180 dias" e o alerta
se chama "Títulos a caminho da baixa (mais de 300 dias)". Escrever "180 dias" é citar o
próprio rótulo, então esses números contam como procedência. Sem isso o verificador
reprovaria a frase mais natural do briefing.

**4. Para cada número do texto, testa os valores que ele pode representar.** `3,52 mi` pode
ser 3,52 ou 3.520.000, e os dois são aceitos, porque o payload guarda o valor cheio e o
texto escreve a forma compacta.

**5. A tolerância sai da precisão do próprio token.** Meia unidade da última casa escrita,
ou 0,1% do valor, o que for maior.

```
"92,5"   casa com 92,5126     uma casa admite meia unidade da última casa
"92,51"  exige mais precisão  duas casas, tolerância dez vezes menor
```

Isso aceita **arredondamento honesto** e recusa **número inventado**, que erra por muito
mais do que uma casa.

**6. Um número sem procedência reprova a resposta inteira.** Não o parágrafo, não a frase: a
resposta.

### O que acontece quando reprova

O app tenta **uma segunda vez**, e a segunda tentativa diz exatamente quais números
reprovaram:

> A tentativa anterior foi descartada: os números X, Y não estão no JSON. Escreva de novo
> usando apenas os valores acima.

Sem essa informação a segunda tentativa seria só um novo sorteio, e o modelo repetiria o
mesmo número.

**Se a segunda também reprovar, a tela não mostra briefing nenhum.** Ela explica que a
leitura não pôde ser gerada.

### Por que falhar é melhor que avisar

A alternativa fácil seria mostrar o texto com um rótulo de "gerado por IA, confira os
números". Foi descartada.

**Um briefing com número inventado é pior que briefing nenhum: ele parece conferido, e
ninguém confere de novo.** O selo de procedência que aparece ao lado do texto aprovado diz
quantos números foram conferidos, e ele só aparece porque a conferência aconteceu de fato.

### Outros três modos de falha que fecham a porta

- **`stop_reason == "max_tokens"`**: texto cortado no meio da frase não vai para a tela.
  Falha direto, sem nova tentativa, porque tentar de novo com o mesmo teto não resolveria.
- **`stop_reason == "refusal"`**: o modelo recusou. A tela diz isso.
- **Erro de rede, credencial ou limite de uso**: mensagem específica para cada um, e o resto
  da página continua válido.

### O verificador é testado sem gastar crédito

`scripts/verificar_leitura.py` cobre o verificador com **18 casos offline**. Ele não chama a
API. Entra na suíte que roda a cada push.

### O que este mecanismo não garante

Vale saber para não prometer demais. Ele garante **procedência numérica**, e só isso. Não
garante que a interpretação seja a melhor possível, nem que o modelo tenha escolhido o
número mais relevante, nem que a frase esteja livre de ênfase indevida.

Ele resolve o modo de falha mais perigoso, que é o número plausível e falso, e não pretende
resolver os outros.

---

## 10. As verificações

Seis portões, **3,5 segundos**, um comando:

```bash
python3 scripts/verificar_tudo.py
```

O mesmo comando roda no GitHub Actions a cada push e a cada pull request, numa máquina
limpa, e a branch principal só aceita merge com ele verde.

| Portão | O que reprova |
|---|---|
| `pyflakes` | erro de sintaxe, import morto, nome indefinido |
| `validar_metricas` | qualquer divergência entre a camada semântica e os números conferidos |
| `verificar_rotulos` | nome de coluna do banco na tela, jargão em prosa, travessão, cifrão cru |
| `verificar_leitura` | falha do verificador de procedência, em 18 casos |
| `verificar_tema` | hexadecimal fora do tema, contraste abaixo do piso, cores indistinguíveis em daltonismo |
| render das páginas | exceção ou aviso de métrica em qualquer uma das cinco |

### As 116 verificações de métrica

`validar_metricas.py` reproduz, de forma independente, cada número publicado e compara.
Cobre faturamento, receita líquida e custo dos três anos, inadimplência em quatro datas, o
aging casa a casa, realizado contra meta, e o nível esperado dos 13 alertas. Saída esperada:
**116/116 obrigatórias**, mais 3 informativas que registram divergências de definição
documentadas.

### A regra que sustenta a suíte

**Todo portão nasceu de um defeito que passou.** E um portão só entra depois de ser provado:
reintroduz-se o defeito, confirma-se que o portão reprova, e só então ele merece confiança.

Portão que nunca falhou não é portão. É decoração que dá sensação de segurança.

### O que os portões não pegam

Eles só pegam o que alguém já aprendeu a checar. Um gráfico de risco por cliente plotava uma
coluna **parecida** com a certa, e mostrava 34 clientes em nível crítico onde a regra
sinalizava 8. Passou pelos seis portões. Caiu na leitura humana de alguém que conhecia o
número esperado.

---

## 11. As invariantes da interface

Seis regras verificadas por script, não combinadas entre pessoas:

- **Só `frotas/metrics/` escreve SQL.** As telas não abrem conexão.
- **A UI não conhece limiar.** Nível e cor de alerta vêm da camada de métricas.
- **A UI não inventa cor.** Zero hexadecimal literal fora do arquivo de tema.
- **Todo número passa pelo formatador**, inclusive os separadores dos gráficos.
- **Nenhum nome de coluna do banco chega à tela.**
- **Nenhum número sem procedência chega à tela**, inclusive os de texto gerado por modelo.

### Três decisões visuais que valem defender

**Cor nunca vem sozinha.** Todo sinal tem um glifo junto: `✓ ! !! ✕ – ┄`. O painel funciona
para quem não distingue vermelho de verde, e a separação das cores em deuteranopia e
protanopia é medida por script.

**Verde é o que é bom para o negócio, não o número positivo.** Custo 5% abaixo da meta é
número negativo e é bom; inadimplência subindo é número positivo e é ruim. Cada indicador
declara a própria direção. É o que impede pintar de verde uma inadimplência que piorou.

**Cinza não é zero.** Ausência de dado e valor zero são coisas diferentes e aparecem
diferentes. Um painel que mostra `0%` num período sem apuração está afirmando algo falso
sobre um período que não aconteceu.

---

## 12. Segurança

- **Não há credencial em lugar nenhum do app.** A única credencial do projeto é a do
  exportador de snapshot, que roda na mão, e a chave opcional da leitura executiva.
- As tabelas são views sobre Parquet abertos em leitura, e uma guarda local recusa qualquer
  SQL que não comece por `SELECT` ou `WITH`. O validador testa as duas barreiras.
- SQL sempre parametrizado. Nenhuma operação de escrita existe no código.
- **A presença da credencial é o interruptor da leitura executiva.** Não existe detecção de
  ambiente: localmente a chave está no `.env` e o botão funciona; na versão publicada o
  segredo não é configurado, o botão aparece desabilitado e o visitante lê o motivo. Um
  caminho de código só, sem sinalizador para alguém esquecer de virar.

---

## 13. Perguntas difíceis, e as respostas

**"Isso não é só um dashboard bonito?"**
A diferença não está no visual, está em três coisas verificáveis: a inadimplência sai pela
metade sem o corte point-in-time, a comparação contra meta inverte de sinal sem o período
casado, e o texto gerado por IA é reprovado quando cita número que não existe. Nenhuma das
três é visual.

**"Por que não fez isso no Power BI?"**
Boa parte daria. O que não daria de forma natural é o corte point-in-time por data de
referência variável, porque ele exige recalcular a foto a cada ponto, e é caro em modelo
tabular. E não daria a suíte de verificação: no Power BI não existe um lugar para 116
asserções que reprovem a publicação.

**"O dataset é sintético. Isso não invalida tudo?"**
Invalida qualquer conclusão sobre uma empresa real, e o projeto diz isso em três lugares. O
que não é sintético é o método: as armadilhas do dado, as definições das métricas e a
verificação funcionariam igual com dado real, porque o problema que elas resolvem é de
definição, não de origem.

**"Você usou IA para escrever o código. O que é seu?"**
As decisões. Escopo, vocabulário de tela, prioridade e toda decisão de negócio. O corte
point-in-time e a comparação por período casado não foram sugestões aceitas, foram decisões
de quem conhece o negócio. E propostas foram revertidas quando não convenceram.

**"Como você sabe que os números estão certos?"**
Não sei por confiança, sei por execução: `python3 scripts/validar_metricas.py` reproduz cada
número publicado de forma independente e compara. Se divergir, quebra.

**"E se a API do Claude cair?"**
O bloco explica que a leitura ficou indisponível e o resto da página continua válido.
Nenhum número da tela depende da IA. Ela é um recurso opcional em cima da camada de
métricas, nunca dentro dela.

**"Por que a leitura executiva está desligada na versão publicada?"**
Porque consome a chave da API, e o painel é público. A escolha foi desligar por ausência de
segredo, em vez de por sinalizador, para não existir um caminho de código que alguém
esqueça de virar.

**"Qual foi o erro mais caro do projeto?"**
Um gráfico que plotava a coluna errada. Mostrava 34 clientes em nível crítico onde a regra
apontava 8, e passou por todos os portões porque a coluna errada é parecida com a certa.
Serviu para entender onde fica a fronteira da verificação automática.

---

## 14. O que ficou de fora, e por quê

- **Margem operacional por contrato:** exigia período casado e um rateio de custo de veículo
  que abria margem para erro silencioso.
- **Análise de recuperação de crédito:** depende de dado de negociação que o conjunto não
  tem.
- **Série retroativa de inadimplência:** cada ponto exige recalcular a foto naquele dia.
  Sustentável para quatro datas conferidas, não para uma série mensal.
- **Concentração de carteira em curva ABC:** virou um top 10 simples, que responde a mesma
  pergunta com menos superfície.
- **Granularidade semanal:** não é omissão. A competência é sempre o dia 1 do mês e a meta é
  mensal por definição. Só a data de pagamento tem grão diário.

Escopo é decisão de risco. Cada item a mais é uma superfície a mais para o número estar
errado sem ninguém perceber.
