import json, os

def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)

bt = load('data/backtest_report.json')
print("backtest_report top-level keys:", list(bt.keys()) if isinstance(bt, dict) else type(bt))
print(json.dumps(bt, ensure_ascii=False, indent=2)[:1500])

print()
fk = load('data/fundamental_kr.json')
print("fundamental_kr type:", type(fk))
if isinstance(fk, list):
    print("len:", len(fk))
    print("first item:", fk[0] if fk else None)
elif isinstance(fk, dict):
    print("keys:", list(fk.keys()))

print()
cpt = load('data/combined_probability_table.json')
print("cpt keys:", list(cpt.keys()) if isinstance(cpt, dict) else type(cpt))
print(json.dumps(cpt, ensure_ascii=False, indent=2)[:1500])

print()
sc = load('data/smallcap_risk_screen.json')
print("sc keys:", list(sc.keys()) if isinstance(sc, dict) else type(sc))
print(json.dumps(sc, ensure_ascii=False, indent=2)[:1500])
