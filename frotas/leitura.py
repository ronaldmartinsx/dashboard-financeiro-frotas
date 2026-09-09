"""Leitura executiva: o briefing do periodo, escrito pelo Claude.

**A regra que sustenta este modulo: o modelo nao tem acesso a dado nenhum.**
Ele nao ve SQL, nao ve o banco e nao calcula. Recebe um dicionario de numeros que
:mod:`frotas.metrics` ja apurou -- os mesmos que as 116 verificacoes cobrem -- e o
trabalho dele e so um: interpretar e priorizar.

E isso e verificado, nao prometido. :func:`conferir` extrai todo numero do texto
gerado e exige que cada um corresponda a um valor do payload, dentro da tolerancia
de arredondamento do proprio texto. Um numero inventado **reprova a resposta**, e a
tela nao mostra briefing nenhum -- do mesmo jeito que a inadimplencia nao aparece
quando a janela de 12 meses esta incompleta. Numero sem procedencia nao vai para a
tela, venha ele de uma consulta errada ou de um modelo.

Degrada em silencio: sem ``ANTHROPIC_API_KEY`` o bloco explica como ligar, e todo o
resto do app continua funcionando igual.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

from frotas import config

#: Nome do segredo. Mesma precedencia dos demais: st.secrets > ambiente > .env.
CHAVE_API: str = "ANTHROPIC_API_KEY"

#: Opus 5. O payload tem ~1.500 tokens e a resposta ~400: alguns centavos por
#: leitura, e ela e sob demanda (botao), nunca no carregamento da pagina.
MODELO: str = "claude-opus-5"

#: Teto de saida. Com pensamento adaptativo, o raciocinio conta neste mesmo teto --
#: com 1.200 a resposta saia cortada no meio da ultima frase. O teto e generoso de
#: proposito: so o que sai de fato e cobrado, e a instrucao de tamanho e que segura
#: o texto em tres paragrafos.
MAX_TOKENS: int = 8000

INSTRUCOES = """Você escreve a leitura executiva de um dashboard financeiro de uma \
locadora de frotas B2B. Quem lê é o CFO.

Você recebe um JSON com números que a camada de métricas do sistema já apurou e \
validou. Seu trabalho é interpretar e priorizar, nunca calcular.

REGRA ABSOLUTA: use somente números que estão no JSON. Não some, não divida, não \
estime, não converta unidade, não arredonde para uma casa que o JSON não tem. Se \
uma afirmação exigir um número que não está lá, escreva a afirmação sem o número \
ou não a escreva. Uma resposta com um número que não veio do JSON é descartada \
inteira por um verificador automático.

COMO ESCREVER:
- Três parágrafos curtos, no máximo quatro linhas cada. Sem título, sem lista, \
sem markdown.
- Primeiro parágrafo: o que está indo bem, com o número que prova.
- Segundo: o que preocupa e por quê.
- Terceiro: a ação mais urgente, e o motivo dela ser urgente.
- No máximo três números por parágrafo. O número entra para sustentar a frase, \
não para preencher. Uma frase inteira de números não se lê.

COMO ESCREVER OS NÚMEROS:
- Valores em reais na forma compacta: "R$ 24,62 mi", "R$ 103,4 mil". Nunca \
"R$ 24.623.638,22".
- Percentuais com uma ou duas casas: "92,51%", "10,02%", "2,8%". Nunca mais \
casas do que o JSON tem.
- Desvio contra meta com sinal: "+2,9%", "+1,22 p.p.".
- Arredondar para menos casas é permitido e desejável. Inventar casa que o JSON \
não tem, não.
- Português do Brasil, vocabulário de negócio. Nada de jargão técnico, nome de \
regra, nome de coluna ou termo em inglês.
- Sem travessão. Use vírgula, ponto ou dois-pontos.
- Não repita o que o número já diz. "A inadimplência está em 10,02%" já informa; \
"a inadimplência, que mede o percentual vencido, está em 10,02%" desperdiça a linha.
- Escreva com convicção. Você está dizendo a alguém o que fazer, não descrevendo \
um gráfico."""


# --------------------------------------------------------------------------
# Verificador
# --------------------------------------------------------------------------

#: Datas em dd/mm/aaaa saem do texto antes da varredura: os pedacos delas nao sao
#: numeros de negocio e nao tem procedencia no payload.
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")

#: Numero em pt-BR, com prefixo e unidade opcionais: "R$ 3,52 mi", "92,5%",
#: "+7,20 p.p.", "44", "1.089".
_NUMERO = re.compile(
    r"""(?:R\$\s*)?                      # prefixo monetario opcional
        (\d{1,3}(?:\.\d{3})+|\d+)        # inteiro, com ou sem separador de milhar
        (?:,(\d+))?                      # parte decimal
        \s*
        (mil|mi|bi|%|p\.p\.)?            # unidade opcional
    """,
    re.VERBOSE | re.IGNORECASE,
)

_MULTIPLICADOR = {"mil": 1_000.0, "mi": 1_000_000.0, "bi": 1_000_000_000.0}


@dataclass(frozen=True)
class Conferencia:
    """Resultado da conferencia de um texto contra o payload."""

    aprovado: bool
    conferidos: int
    sem_procedencia: tuple[str, ...] = field(default=())

    @property
    def resumo(self) -> str:
        if self.aprovado:
            plural = "s" if self.conferidos != 1 else ""
            return f"{self.conferidos} número{plural} conferido{plural} contra a camada de métricas"
        return f"{len(self.sem_procedencia)} número sem procedência: {', '.join(self.sem_procedencia)}"


def _numeros_do_payload(dados: Any, saida: set[float] | None = None) -> set[float]:
    """Todo numero do payload, em qualquer profundidade -- inclusive dentro de texto.

    Os rotulos tambem carregam numero: a faixa se chama "Mais de 180 dias" e o
    alerta se chama "Títulos a caminho da baixa (mais de 300 dias)". Escrever "180
    dias" e citar o proprio rotulo, entao esses numeros contam como procedencia.
    Sem isto o verificador reprovaria a frase mais natural do briefing.
    """
    saida = set() if saida is None else saida
    if isinstance(dados, bool):
        return saida
    if isinstance(dados, (int, float)):
        valor = float(dados)
        if valor == valor:  # descarta NaN
            saida.add(abs(valor))
    elif isinstance(dados, str):
        for achado in _NUMERO.finditer(dados):
            for candidato in _candidatos(achado.group(1), achado.group(2), achado.group(3)):
                saida.add(abs(candidato))
    elif isinstance(dados, Mapping):
        for item in dados.values():
            _numeros_do_payload(item, saida)
    elif isinstance(dados, (list, tuple)):
        for item in dados:
            _numeros_do_payload(item, saida)
    return saida


def _candidatos(inteiro: str, decimal: str | None, unidade: str | None) -> list[float]:
    """Valores que o token pode representar.

    "3,52 mi" pode ser 3,52 ou 3.520.000 -- os dois sao aceitos, porque o payload
    guarda o valor cheio e o texto costuma escrever a forma compacta.
    """
    bruto = inteiro.replace(".", "") + ("." + decimal if decimal else "")
    try:
        base = float(bruto)
    except ValueError:
        return []
    valores = [base]
    fator = _MULTIPLICADOR.get((unidade or "").lower())
    if fator:
        valores.append(base * fator)
    return valores


def conferir(texto: str, payload: Mapping[str, Any]) -> Conferencia:
    """Todo numero do texto tem origem no payload?

    A tolerancia sai da **precisao do proprio token**: "92,5" casa com 92,5126
    porque uma casa decimal admite meia unidade da ultima casa; "92,51" exige
    precisao maior. Isso aceita o arredondamento honesto e recusa o numero
    inventado, que erra por muito mais do que uma casa.
    """
    permitidos = _numeros_do_payload(payload)
    limpo = _DATA.sub(" ", texto)

    conferidos = 0
    orfaos: list[str] = []
    for achado in _NUMERO.finditer(limpo):
        inteiro, decimal, unidade = achado.group(1), achado.group(2), achado.group(3)
        casas = len(decimal) if decimal else 0
        conferidos += 1
        casou = False
        for candidato in _candidatos(inteiro, decimal, unidade):
            # Meia unidade da ultima casa escrita, ou 0,1% do valor -- o que for
            # maior. O segundo termo cobre o compacto ("3,52 mi" para 3.519.484).
            for alvo in permitidos:
                folga = max(0.5 * (10 ** -casas), 0.001 * alvo)
                if abs(candidato - alvo) <= folga:
                    casou = True
                    break
            if casou:
                break
        if not casou:
            orfaos.append(achado.group(0).strip())

    return Conferencia(not orfaos, conferidos, tuple(dict.fromkeys(orfaos)))


# --------------------------------------------------------------------------
# Payload
# --------------------------------------------------------------------------


def _num(valor: Any) -> float | None:
    """Converte para float simples, ou None -- o JSON nao aceita NaN nem numpy.

    Arredonda em **duas casas**, a mesma precisao que o app publica. Nao e cosmetico:
    o modelo escreve o que le, e um payload com ``2.8411`` produzia "2,8411%" na tela.
    O jeito de impedir precisao falsa no texto e nao ter precisao falsa no payload.
    """
    try:
        saida = float(valor)
    except (TypeError, ValueError):
        return None
    return None if saida != saida else round(saida, 2)


def montar_payload(
    *,
    exercicio: int,
    data_ref: date,
    resumo: Mapping[str, Any] | None,
    cobertura: Mapping[str, Any] | None,
    inadimplencia: Mapping[str, Any] | None,
    metas_do_ano: list[Mapping[str, Any]],
    alertas: list[Mapping[str, Any]],
    segmentos: list[Mapping[str, Any]],
    aging: list[Mapping[str, Any]],
    ociosidade: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Monta o dicionario que vai para o modelo.

    Cada chave e um rotulo de negocio, nao um nome de coluna: o modelo escreve o
    que le, e um payload com ``pct_vencido_30d`` acabaria com isso na tela.
    """

    def campos(origem: Mapping[str, Any] | None, mapa: Mapping[str, str]) -> dict[str, Any]:
        if origem is None:
            return {}
        saida = {}
        for coluna, rotulo in mapa.items():
            valor = _num(origem.get(coluna))
            if valor is not None:
                saida[rotulo] = valor
        return saida

    return {
        "contexto": {
            "exercicio": exercicio,
            "data_da_leitura": data_ref.strftime("%d/%m/%Y"),
        },
        "constantes_do_negocio": {
            "dias_para_a_fatura_virar_inadimplencia": config.DIAS_CARENCIA_INADIMPLENCIA,
            "meses_da_janela_da_inadimplencia": config.MESES_JANELA_INADIMPLENCIA,
            "dias_para_a_fatura_ser_baixada": 365,
        },
        "faturamento_do_periodo": campos(resumo, {
            "faturamento_bruto": "faturamento_bruto_reais",
            "receita_liquida": "receita_liquida_reais",
            "impostos": "impostos_reais",
            "valor_cancelado": "cancelado_reais",
            "pct_cancelado": "cancelado_pct_do_faturado",
            "ticket_medio": "ticket_medio_reais",
            "qtd_titulos": "quantidade_de_faturas",
        }),
        "caixa": campos(cobertura, {
            "recebimento_12m": "recebido_em_12_meses_reais",
            "cobertura_pct": "cobertura_de_caixa_pct",
            "faturamento_valido_12m": "faturado_das_mesmas_12_competencias_reais",
        }),
        "inadimplencia_na_data": campos(inadimplencia, {
            "inadimplencia_pct": "inadimplencia_acima_de_30_dias_pct",
            "valor_vencido_30d": "valor_vencido_reais",
            "qtd_titulos_vencidos": "quantidade_de_faturas_vencidas",
        }),
        "realizado_contra_meta": [
            {
                "indicador": str(linha.get("tipo_meta")),
                "unidade": str(linha.get("unidade")),
                "realizado": _num(linha.get("realizado")),
                "meta_do_mesmo_periodo": _num(linha.get("meta_alinhada")),
                "desvio_pct": _num(linha.get("variacao_pct_alinhada")),
                "desvio_pontos_percentuais": _num(linha.get("variacao_abs")),
            }
            for linha in metas_do_ano
        ],
        "alertas_ativos": [
            {
                "assunto": str(a.get("titulo")),
                "nivel": str(a.get("nivel")),
                "valor": _num(a.get("valor")),
                "unidade": str(a.get("unidade")),
                "vira_atencao_em": _num(a.get("limiar_ambar")),
                "vira_critico_em": _num(a.get("limiar_vermelho")),
            }
            for a in alertas
        ],
        "inadimplencia_por_segmento": [
            {
                "segmento": str(s.get("segmento")),
                "inadimplencia_pct": _num(s.get("inadimplencia_pct")),
                "vencido_reais": _num(s.get("vencido_30d_mais")),
                "clientes": _num(s.get("qtd_clientes")),
            }
            for s in segmentos
        ],
        "carteira_por_faixa_de_atraso": [
            {
                "faixa": str(f.get("faixa")),
                "valor_reais": _num(f.get("valor_bruto")),
                "faturas": _num(f.get("qtd_titulos")),
                "pct_da_carteira": _num(f.get("participacao_pct")),
            }
            for f in aging
        ],
        "frota_parada_no_ultimo_mes": campos(ociosidade, {
            "taxa_ociosidade_pct": "parcela_da_frota_sem_contrato_pct",
            "custo_ocioso": "custo_do_veiculo_parado_reais",
            "qtd_veiculos_ociosos": "veiculos_parados",
            "qtd_veiculos_frota": "veiculos_na_frota",
            "pct_do_custo_total": "peso_no_custo_do_mes_pct",
        }),
    }


# --------------------------------------------------------------------------
# Chamada
# --------------------------------------------------------------------------


class LeituraIndisponivel(RuntimeError):
    """Nao foi possivel gerar a leitura. ``mensagem_usuario`` esta pronta para a tela."""

    def __init__(self, mensagem_usuario: str, detalhe: str = "") -> None:
        super().__init__(mensagem_usuario)
        self.mensagem_usuario = mensagem_usuario
        self.detalhe = detalhe


@dataclass(frozen=True)
class Leitura:
    """O briefing aprovado, com o que custou e o que foi conferido."""

    texto: str
    conferencia: Conferencia
    tokens_entrada: int
    tokens_saida: int
    tentativas: int

    @property
    def custo_estimado_reais(self) -> float:
        """Opus 5 a US$ 5 e US$ 25 por milhao de tokens, a um dolar arredondado."""
        dolar = 5.40
        usd = self.tokens_entrada / 1e6 * 5.0 + self.tokens_saida / 1e6 * 25.0
        return usd * dolar


def disponivel() -> bool:
    """Ha credencial da API configurada?"""
    return bool(config.obter_segredo(CHAVE_API))


def gerar(payload: Mapping[str, Any], *, tentativas: int = 2) -> Leitura:
    """Pede a leitura ao modelo e so devolve o que passar na conferencia.

    Tenta ``tentativas`` vezes. Se a conferencia reprovar todas, levanta
    :class:`LeituraIndisponivel` -- **a tela nao mostra texto reprovado**. Um
    briefing com numero inventado e pior que briefing nenhum: ele parece
    conferido e ninguem confere de novo.
    """
    chave = config.obter_segredo(CHAVE_API)
    if not chave:
        raise LeituraIndisponivel(
            "A leitura executiva precisa de uma credencial da API do Claude. "
            f"Defina {CHAVE_API} em .streamlit/secrets.toml, na variável de ambiente "
            "ou no .env da raiz.",
            detalhe="credencial",
        )
    try:
        import anthropic
    except ImportError:
        raise LeituraIndisponivel(
            "A biblioteca anthropic não está instalada. Rode: pip install -r requirements.txt",
            detalhe="anthropic ausente",
        ) from None

    cliente = anthropic.Anthropic(api_key=chave)
    corpo = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    ultima: Conferencia | None = None

    for tentativa in range(1, tentativas + 1):
        pedido = corpo
        if ultima is not None and ultima.sem_procedencia:
            # A segunda tentativa diz exatamente o que reprovou. Sem isso ela seria
            # so um novo sorteio, e o modelo repetiria o mesmo numero.
            pedido += (
                "\n\nA tentativa anterior foi descartada: os números "
                f"{', '.join(ultima.sem_procedencia)} não estão no JSON. "
                "Escreva de novo usando apenas os valores acima."
            )
        try:
            resposta = cliente.messages.create(
                model=MODELO,
                max_tokens=MAX_TOKENS,
                system=INSTRUCOES,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": pedido}],
            )
        except anthropic.AuthenticationError:
            raise LeituraIndisponivel(
                "A credencial da API do Claude foi recusada. Verifique o valor de "
                f"{CHAVE_API}.",
                detalhe="autenticacao",
            ) from None
        except anthropic.RateLimitError:
            raise LeituraIndisponivel(
                "A API do Claude está com limite de uso atingido. Tente de novo em alguns minutos.",
                detalhe="rate_limit",
            ) from None
        except anthropic.APIStatusError as exc:
            raise LeituraIndisponivel(
                "A API do Claude não respondeu como esperado. A leitura executiva "
                "ficou indisponível; o resto da página continua válido.",
                detalhe=f"http {exc.status_code}",
            ) from None
        except anthropic.APIConnectionError:
            raise LeituraIndisponivel(
                "Não foi possível falar com a API do Claude. Verifique a conexão.",
                detalhe="conexao",
            ) from None

        if resposta.stop_reason == "refusal":
            raise LeituraIndisponivel(
                "O modelo recusou gerar a leitura para estes dados.", detalhe="refusal",
            )
        if resposta.stop_reason == "max_tokens":
            # Texto cortado no meio da frase nao vai para a tela. Nao adianta tentar
            # de novo com o mesmo teto, entao falha direto.
            raise LeituraIndisponivel(
                "A leitura saiu longa demais e foi cortada. Tente de novo.",
                detalhe="max_tokens",
            )

        texto = "\n\n".join(
            bloco.text.strip() for bloco in resposta.content
            if bloco.type == "text" and bloco.text.strip()
        )
        conferencia = conferir(texto, payload)
        if conferencia.aprovado and texto:
            return Leitura(
                texto=texto,
                conferencia=conferencia,
                tokens_entrada=resposta.usage.input_tokens,
                tokens_saida=resposta.usage.output_tokens,
                tentativas=tentativa,
            )
        ultima = conferencia

    detalhe = ", ".join(ultima.sem_procedencia) if ultima else "resposta vazia"
    raise LeituraIndisponivel(
        "A leitura gerada citou números que não vieram da camada de métricas, "
        "então ela foi descartada. Os números da página continuam válidos.",
        detalhe=detalhe,
    )
