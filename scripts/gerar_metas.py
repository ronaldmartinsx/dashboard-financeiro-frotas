"""Gera public.metas: orcamento coerente por construcao (mes -> trimestre -> ano)."""
import csv, calendar, os, sys
from collections import defaultdict
from pathlib import Path
import psycopg2

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = sys.argv[1] if len(sys.argv) > 1 else str(RAIZ / 'metas_geradas.csv')

def realizado():
    """Series realizadas que calibram o orcamento, direto do banco."""
    for linha in (RAIZ / '.env').read_text().splitlines():
        linha = linha.strip()
        if linha and not linha.startswith('#') and '=' in linha:
            k, v = linha.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    with psycopg2.connect(os.environ['PG_DSN']) as c, c.cursor() as cur:
        cur.execute("""
            select to_char(t.competencia,'YYYY-MM'), cl.segmento,
                   sum(t.valor_bruto)::float, sum(t.valor_liquido)::float
            from public.titulos_receber t join public.clientes cl using (id_cliente)
            group by 1,2""")
        fat = cur.fetchall()
        cur.execute("""
            select to_char(t.data_pagamento,'YYYY-MM'), cl.segmento, sum(t.valor_pago)::float
            from public.titulos_receber t join public.clientes cl using (id_cliente)
            where t.data_pagamento is not null group by 1,2""")
        rec = cur.fetchall()
        cur.execute("select to_char(competencia,'YYYY-MM'), sum(valor)::float from public.custos group by 1")
        cus = cur.fetchall()
        # inadimplencia > 30d point-in-time (definicao do DICIONARIO_DADOS.md)
        cur.execute("""
            with refs as (select (generate_series('2024-01-01'::date,'2026-08-01'::date,'1 month')
                                  + interval '1 month - 1 day')::date ref)
            select to_char(r.ref,'YYYY-MM'),
              (select coalesce(sum(valor_bruto),0) from public.titulos_receber t
                where t.data_vencimento <= r.ref - 30
                  and (t.data_pagamento is null or t.data_pagamento > r.ref)
                  and (t.data_cancelamento is null or t.data_cancelamento > r.ref))::float,
              (select coalesce(sum(valor_bruto),0) from public.titulos_receber t
                where t.competencia > (date_trunc('month', r.ref) - interval '12 months')::date
                  and t.competencia <= date_trunc('month', r.ref)::date
                  and (t.data_cancelamento is null or t.data_cancelamento > r.ref))::float
            from refs r""")
        inad = cur.fetchall()
    return {'fat_seg': fat, 'rec_seg': rec, 'custos': cus, 'inad': inad}

R = realizado()

SEGS = ['Agronegocio','Construcao Civil','Energia e Saneamento','Industria',
        'Logistica e Transporte','Mineracao','Servicos Publicos','Varejo e Distribuicao']
MESES = lambda a: [f'{a}-{m:02d}' for m in range(1, 13)]
c = lambda x: int(round(x * 100))          # reais -> centavos

# ---------- realizado ----------
fat_seg, rl_seg, rec_seg = defaultdict(dict), defaultdict(dict), defaultdict(dict)
for m, s, b, l in R['fat_seg']:
    fat_seg[m][s] = c(b); rl_seg[m][s] = c(l)
for m, s, v in R['rec_seg']:
    rec_seg[m][s] = c(v)
custo_real = {m: c(v) for m, v in R['custos']}
inad_real = {m: round(100 * v / f, 2) for m, v, f in R['inad']}
fat_real = {m: sum(d.values()) for m, d in fat_seg.items()}
rec_real = {m: sum(d.values()) for m, d in rec_seg.items()}

def perfil(base, ano, suave=0.45):
    """Sazonalidade do ano-base, achatada em direcao ao uniforme (orcamento nao copia ruido)."""
    v = [base.get(m, 0) for m in MESES(ano)]
    t = sum(v) or 1
    p = [(1 - suave) * x / t + suave / 12 for x in v]
    return [x / sum(p) for x in p]

def repartir(total, pesos):
    """Distribui inteiro por maior-resto: soma das partes == total, exatamente."""
    bruto = [total * p for p in pesos]
    parte = [int(x) for x in bruto]
    resto = sorted(range(len(pesos)), key=lambda i: bruto[i] - parte[i], reverse=True)
    for i in range(total - sum(parte)):
        parte[resto[i % len(resto)]] += 1
    return parte

# ---------- premissas de planejamento ----------
ALIQ_LIQ   = 0.9375                                    # receita liquida / faturamento (mix 3,65%/8,65%)
PESO_CAIXA = [0.56, 0.30, 0.14]                        # recebimento em m-1, m-2, m-3 (defasagem observada)
FORMA_MARGEM = [0.8, 0.6, 0.2, 0.0, -0.4, -0.6, -0.8, -0.6, -0.2, 0.2, 0.4, 0.4]  # p.p. de sazonalidade

PLANOS = [
    # ano, versao, vigente, faturamento anual alvo, margem alvo, eficiencia de cobranca, meta de inadimplencia (12 meses)
    (2024, 'Orcamento Original', True,  30_600_000, 0.350, 0.97,
     [3.50,3.40,3.30,3.20,3.10,3.00,3.00,3.00,3.00,3.00,3.00,3.00]),
    (2025, 'Orcamento Original', True,  32_800_000, 0.355, 0.97,
     [3.50,3.40,3.40,3.30,3.20,3.20,3.10,3.10,3.00,3.00,3.00,3.00]),
    (2026, 'Orcamento Original', False, 37_800_000, 0.350, 0.97,
     [10.00,9.60,9.20,8.80,8.40,8.00,7.70,7.40,7.10,6.90,6.70,6.50]),
    (2026, 'Revisao 2026',       True,  None,       0.330, 0.93,
     [None,None,None,9.60,9.40,9.20,9.00,8.80,8.60,8.40,8.20,8.00]),
]
CORTE_REVISAO = 3          # revisao de abr/2026: jan-mar fechados no realizado
FATOR_REVISAO = 0.94       # faturamento de abr-dez revisado para baixo

fat_plano = {}   # mes -> centavos, alimenta a defasagem de caixa do ano seguinte
linhas = []

for ano, versao, vigente, fat_alvo, margem_alvo, efic, meta_inad in PLANOS:
    meses = MESES(ano)
    revisao = versao == 'Revisao 2026'
    base = ano - 1 if ano > 2024 else 2024          # 2024 nao tem ano anterior no dataset

    # --- faturamento e receita liquida, por segmento ---
    fat, rl = {}, {}
    if not revisao:
        pm = perfil(fat_real, base)
        tot_seg = {s: sum(fat_seg[x].get(s, 0) for x in MESES(base)) for s in SEGS}
        t = sum(tot_seg.values())
        share = [0.6 * tot_seg[s] / t + 0.4 / 8 for s in SEGS]
        share = [x / sum(share) for x in share]
        mensal = repartir(c(fat_alvo), pm)
        for i, m in enumerate(meses):
            fat[m] = dict(zip(SEGS, repartir(mensal[i], share)))
            rl[m] = dict(zip(SEGS, repartir(int(round(mensal[i] * ALIQ_LIQ)), share)))
    else:
        for i, m in enumerate(meses):
            if i < CORTE_REVISAO:
                fat[m] = dict(fat_seg[m]); rl[m] = dict(rl_seg[m])   # meses fechados: realizado
        tot_seg = {s: sum(fat_seg[x].get(s, 0) for x in MESES(2025)) for s in SEGS}
        t = sum(tot_seg.values())
        share = [0.6 * tot_seg[s] / t + 0.4 / 8 for s in SEGS]
        share = [x / sum(share) for x in share]
        for i, m in enumerate(meses):
            if i < CORTE_REVISAO: continue
            tot = int(round(fat_orig_mes[m] * FATOR_REVISAO))
            fat[m] = dict(zip(SEGS, repartir(tot, share)))
            rl[m] = dict(zip(SEGS, repartir(int(round(tot * ALIQ_LIQ)), share)))

    fat_mes = {m: sum(fat[m].values()) for m in meses}
    rl_mes = {m: sum(rl[m].values()) for m in meses}
    if not revisao and ano == 2026:
        fat_orig_mes = dict(fat_mes)
    if not revisao:
        fat_plano.update(fat_mes)

    # --- custo operacional: derivado da margem alvo (mes fechado = realizado) ---
    rl_ano = sum(rl_mes.values())
    custo_travado = sum(custo_real[meses[i]] for i in range(CORTE_REVISAO)) if revisao else 0
    rl_travado = sum(rl_mes[meses[i]] for i in range(CORTE_REVISAO)) if revisao else 0
    custo_ano = int(round(rl_ano * (1 - margem_alvo)))          # margem anual bate exatamente
    livres = [i for i in range(12) if not (revisao and i < CORTE_REVISAO)]
    bruto = [rl_mes[meses[i]] * (1 - (margem_alvo + FORMA_MARGEM[i] / 100)) for i in livres]
    partes = repartir(custo_ano - custo_travado, [x / sum(bruto) for x in bruto])
    custo = {}
    for i in range(12):
        custo[meses[i]] = custo_real[meses[i]] if (revisao and i < CORTE_REVISAO) else partes[livres.index(i)]

    # --- recebimento: cobranca do faturado com a defasagem observada ---
    def fat_ant(m, k):
        a, mm = int(m[:4]), int(m[5:]) - k
        while mm < 1: mm += 12; a -= 1
        return fat_plano.get(f'{a}-{mm:02d}', 0)
    tot_rec = {s: sum(rec_seg[x].get(s, 0) for x in MESES(base)) for s in SEGS}
    t = sum(tot_rec.values())
    share_rec = [0.6 * tot_rec[s] / t + 0.4 / 8 for s in SEGS]
    share_rec = [x / sum(share_rec) for x in share_rec]
    rec = {}
    for i, m in enumerate(meses):
        if revisao and i < CORTE_REVISAO:
            rec[m] = dict(rec_seg.get(m, {s: 0 for s in SEGS})); continue
        prev = [fat_mes[meses[i-k]] if i - k >= 0 else fat_ant(m, k) for k in (1, 2, 3)]
        if revisao:
            prev = [int(round(p * FATOR_REVISAO)) if i - k >= CORTE_REVISAO else p
                    for k, p in zip((1, 2, 3), prev)]
        tot = int(round(efic * sum(w * p for w, p in zip(PESO_CAIXA, prev))))
        rec[m] = dict(zip(SEGS, repartir(tot, share_rec)))
    rec_mes = {m: sum(rec[m].values()) for m in meses}

    # --- emissao das linhas ---
    def periodo(gran, i):
        if gran == 'Mensal':
            a, mm = ano, i + 1
            return (f'T{(mm-1)//3+1}', f'{ano}-{mm:02d}',
                    f'{ano}-{mm:02d}-01', f'{ano}-{mm:02d}-{calendar.monthrange(ano,mm)[1]}')
        if gran == 'Trimestral':
            mm = i * 3 + 1
            return (f'T{i+1}', None, f'{ano}-{mm:02d}-01',
                    f'{ano}-{mm+2:02d}-{calendar.monthrange(ano,mm+2)[1]}')
        return (None, None, f'{ano}-01-01', f'{ano}-12-31')

    def add(tipo, unidade, agreg, nivel, chave, gran, i, valor):
        tri, am, ini, fim = periodo(gran, i)
        linhas.append([None, versao, '1' if vigente else '0', tipo, unidade, agreg, gran,
                       nivel, chave, ano, tri, am, ini, fim, valor])

    janelas = {'Mensal': [[i] for i in range(12)],
               'Trimestral': [[3*q+k for k in range(3)] for q in range(4)],
               'Anual': [list(range(12))]}

    for tipo, serie_seg, serie_tot in (('Faturamento', fat, fat_mes),
                                       ('Receita Liquida', rl, rl_mes),
                                       ('Recebimento (Caixa)', rec, rec_mes)):
        for gran, js in janelas.items():
            for i, idx in enumerate(js):
                add(tipo, 'BRL', 'Soma', 'Empresa', 'TOTAL', gran, i,
                    f'{sum(serie_tot[meses[j]] for j in idx)/100:.2f}')
                for s in SEGS:
                    add(tipo, 'BRL', 'Soma', 'Segmento', s, gran, i,
                        f'{sum(serie_seg[meses[j]].get(s,0) for j in idx)/100:.2f}')

    for gran, js in janelas.items():
        for i, idx in enumerate(js):
            add('Custo Operacional', 'BRL', 'Soma', 'Empresa', 'TOTAL', gran, i,
                f'{sum(custo[meses[j]] for j in idx)/100:.2f}')
            r = sum(rl_mes[meses[j]] for j in idx); k = sum(custo[meses[j]] for j in idx)
            add('Margem Operacional', '%', 'Media Ponderada', 'Empresa', 'TOTAL', gran, i,
                f'{100*(r-k)/r:.2f}')
            fim = idx[-1]
            v = meta_inad[fim] if meta_inad[fim] is not None else inad_real[meses[fim]]
            add('Inadimplencia > 30d', '%', 'Fim de Periodo', 'Empresa', 'TOTAL', gran, i, f'{v:.2f}')

for n, l in enumerate(linhas, 1):
    l[0] = f'MET{n:05d}'

with open(SAIDA, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['id_meta','versao_meta','eh_versao_vigente','tipo_meta','unidade','tipo_agregacao',
                'granularidade','nivel_analise','chave_nivel','ano','trimestre','ano_mes',
                'data_inicio_periodo','data_fim_periodo','valor_meta'])
    w.writerows(linhas)
print(f'{len(linhas)} linhas geradas em {SAIDA}')
