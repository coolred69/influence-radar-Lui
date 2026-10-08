import json, os

def load(p):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {"__error__": str(e)}

ind = load('data/indicator_results.json')
bt = load('data/backtest_report.json')
td = load('data/training_data.json')
fu = load('data/fundamental_us.json')
fk = load('data/fundamental_kr.json')
cpt = load('data/combined_probability_table.json')
sc = load('data/smallcap_risk_screen.json')

print("=== indicator_results ===")
print("generation:", ind.get('generation'))
print("coordinate_sig:", ind.get('coordinate_sig'))
print("optimal_metrics:", ind.get('optimal_metrics'))
print("has best_ever key:", 'best_ever' in ind)
w = ind.get('optimal_weights', {})
print("hit_rate:", w.get('hit_rate'), "sentiment:", w.get('sentiment'))
print("dep_sum(hit_rate+sentiment):", (w.get('hit_rate') or 0) + (w.get('sentiment') or 0))

print()
print("=== backtest_report ===")
res = bt.get('results', bt)
print("total_signals:", res.get('total_signals'))
print("accuracy:", res.get('accuracy'))
print("avg_return:", res.get('avg_return'))
print("positive_return_rate:", res.get('positive_return_rate'))

print()
print("=== training_data ===")
print("total_signals:", td.get('total_signals'))

print()
print("=== fundamental_us ===")
print("generated_at:", fu.get('generated_at'))
print()
print("=== fundamental_kr ===")
print("generated_at:", fk.get('generated_at'))
print()
print("=== combined_probability_table ===")
print("generated_at:", cpt.get('generated_at'))
rows = cpt.get('table') or cpt.get('results') or cpt.get('data')
print("top-level keys:", list(cpt.keys()))

print()
print("=== smallcap_risk_screen ===")
print("generated_at:", sc.get('generated_at'))
print("excluded_count:", sc.get('excluded_count'))
print("flagged_count:", sc.get('flagged_count'))
print("clean_count:", sc.get('clean_count'))
results = sc.get('results', [])
excluded = [r.get('ticker') or r.get('name') or r.get('symbol') for r in results if r.get('excluded')]
print("excluded names:", excluded)

print()
print("=== env keys check ===")
envp = '.env'
if os.path.exists(envp):
    with open(envp, encoding='utf-8') as f:
        keys = [line.split('=')[0] for line in f if '=' in line and not line.strip().startswith('#')]
    print("DART_API_KEY present:", 'DART_API_KEY' in keys)
    print("FMP_API_KEY present:", 'FMP_API_KEY' in keys)
else:
    print(".env not found")
