import json, os

def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)

out = open('_tmp_health_out2.txt', 'w', encoding='utf-8')
def P(*a):
    print(*a, file=out)

ind = load('data/indicator_results.json')
P("best_ever:", json.dumps(ind.get('best_ever'), ensure_ascii=False))

# backtest_report at repo root per 10/6 log note
for cand in ['backtest_report.json', 'data/backtest_report.json']:
    if os.path.exists(cand):
        bt = load(cand)
        P(f"=== {cand} FOUND ===")
        P(json.dumps(bt, ensure_ascii=False, indent=2)[:1000])
    else:
        P(f"{cand} NOT FOUND")

# .env keys
if os.path.exists('.env'):
    with open('.env', encoding='utf-8') as f:
        lines = [l.split('=')[0].strip() for l in f if '=' in l and not l.strip().startswith('#')]
    P("DART_API_KEY in .env:", 'DART_API_KEY' in lines)
    P("FMP_API_KEY in .env:", 'FMP_API_KEY' in lines)
else:
    P(".env NOT FOUND")

# fundamental_kr file mtime
import datetime
mtime = os.path.getmtime('data/fundamental_kr.json')
P("fundamental_kr.json mtime (local):", datetime.datetime.fromtimestamp(mtime))
mtime2 = os.path.getmtime('data/fundamental_us.json')
P("fundamental_us.json mtime (local):", datetime.datetime.fromtimestamp(mtime2))

# top3 combined table check (already have via generated_at) - rows sorted
cpt = load('data/combined_probability_table.json')
rows = sorted(cpt.get('rows', []), key=lambda r: r.get('final_score', 0), reverse=True)[:3]
P("top3:", [(r['ticker'], r['final_score']) for r in rows])

sc = load('data/smallcap_risk_screen.json')
P("sc excluded_count/flagged/clean:", sc.get('excluded_count'), sc.get('flagged_count'), sc.get('clean_count'))
excluded_names = [r.get('name') for r in sc.get('results', []) if r.get('excluded')]
P("excluded names:", excluded_names)

out.close()
print("DONE")
