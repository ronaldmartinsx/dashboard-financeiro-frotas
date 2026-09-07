"""Testa o verificador de procedencia da leitura executiva, sem chamar a API.

O verificador e a unica coisa que separa "briefing confiavel" de "texto plausivel".
Se ele falhar aberto, o app passa a exibir numero inventado com cara de conferido --
que e pior do que nao ter briefing. Por isso ele tem teste proprio, e o teste roda
offline: nao gasta credito e nao depende de rede.

    python3 scripts/verificar_leitura.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frotas.leitura import conferir  # noqa: E402

VERDE, VERMELHO, CINZA, FIM = "\033[32m", "\033[31m", "\033[90m", "\033[0m"

#: Um payload de brinquedo com a forma do real: aninhado, com lista e com os
#: mesmos numeros que aparecem no app.
PAYLOAD = {
    "contexto": {"exercicio": 2026, "data_da_leitura": "31/08/2026"},
    "caixa": {"cobertura_de_caixa_pct": 92.5126, "recebido_em_12_meses_reais": 32957000.0},
    "inadimplencia_na_data": {
        "inadimplencia_acima_de_30_dias_pct": 10.0213,
        "valor_vencido_reais": 3519484.2,
        "quantidade_de_faturas_vencidas": 129,
    },
    "alertas_ativos": [
        {"assunto": "Cobertura de caixa", "valor": 92.5126, "vira_critico_em": 93.0},
        {"assunto": "Taxa de ociosidade", "valor": 6.2762, "vira_critico_em": 6.0},
    ],
    "inadimplencia_por_segmento": [
        {"segmento": "Construcao Civil", "inadimplencia_pct": 18.0728,
         "vencido_reais": 900175.56, "clientes": 10},
    ],
    "constantes_do_negocio": {"dias_para_a_fatura_virar_inadimplencia": 30,
                              "dias_para_a_fatura_ser_baixada": 365},
}

#: ``(rotulo, texto, deve_aprovar)``. Os casos de reprovacao sao os que importam:
#: um verificador que aprova tudo passa em qualquer teste de aprovacao.
CASOS: list[tuple[str, str, bool]] = [
    ("valor exato",
     "A cobertura de caixa está em 92,51%.", True),
    ("arredondado para uma casa",
     "A cobertura de caixa está em 92,5%.", True),
    ("arredondado para inteiro",
     "A inadimplência está em 10%.", True),
    ("forma compacta em milhões",
     "São R$ 3,52 mi vencidos na data.", True),
    ("forma compacta em milhares",
     "Construção Civil tem R$ 900,2 mil vencidos.", True),
    ("valor cheio com separador de milhar",
     "O vencido soma R$ 3.519.484,20.", True),
    ("contagem inteira",
     "São 129 faturas vencidas em 10 clientes.", True),
    ("limiar do alerta",
     "A cobertura rompeu o piso de 93,0%.", True),
    ("constante de negócio",
     "Vencido há mais de 30 dias, e a baixa ocorre aos 365 dias.", True),
    ("data no texto não é número de negócio",
     "Na leitura de 31/08/2026 a carteira estava assim.", True),
    ("ano do exercício",
     "O exercício de 2026 segue acima do plano.", True),
    ("texto sem número nenhum",
     "O caixa acompanha o faturamento e a cobrança preocupa.", True),

    ("número inventado do nada",
     "A margem operacional ficou em 24,7%.", False),
    ("soma feita pelo modelo",
     "Somando as duas faixas, são R$ 1,59 mi vencidos.", False),
    ("percentual plausível mas ausente",
     "A inadimplência subiu 3,4 pontos percentuais no trimestre.", False),
    ("valor certo com unidade trocada",
     "São R$ 3,52 mil vencidos na data.", False),
    ("contagem inventada",
     "São 212 faturas vencidas.", False),
    ("um número certo e outro inventado",
     "A cobertura está em 92,51% e a ociosidade em 9,9%.", False),
]


def main() -> int:
    falhas = 0
    print(f"{CINZA}Verificador de procedência da leitura executiva{FIM}\n")
    for rotulo, texto, esperado in CASOS:
        resultado = conferir(texto, PAYLOAD)
        ok = resultado.aprovado == esperado
        falhas += not ok
        marca = f"{VERDE}ok{FIM}" if ok else f"{VERMELHO}FALHA{FIM}"
        veredito = "aprovou" if resultado.aprovado else "reprovou"
        detalhe = ""
        if not resultado.aprovado:
            detalhe = f"  {CINZA}órfãos: {', '.join(resultado.sem_procedencia)}{FIM}"
        print(f"  {marca}  {rotulo:42} {veredito}{detalhe}")

    print()
    if falhas:
        print(f"{VERMELHO}{falhas} de {len(CASOS)} casos falharam.{FIM}")
        return 1
    print(f"{VERDE}Os {len(CASOS)} casos passaram.{FIM} "
          f"{CINZA}Nenhum número inventado passaria para a tela.{FIM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
