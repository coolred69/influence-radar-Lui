import json

def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)

for name in ['training_data.json', 'overfit_report.json', 'optimal_params.json']:
    d = load('data/' + name)
    print(f"=== {name} ===")
    print("type:", type(d))
    if isinstance(d, dict):
        print("keys:", list(d.keys()))
        print(json.dumps(d, ensure_ascii=False, indent=2)[:1200])
    elif isinstance(d, list):
        print("len:", len(d))
        print(json.dumps(d[:2], ensure_ascii=False, indent=2))
    print()

fk = load('data/fundamental_kr.json')
print("=== fundamental_kr ===")
print("type:", type(fk), "len:", len(fk) if isinstance(fk,(list,dict)) else '')
if isinstance(fk, list) and fk:
    print(json.dumps(fk[0], ensure_ascii=False, indent=2)[:800])

cpt = load('data/combined_probability_table.json')
print("=== combined_probability_table ===")
print("type:", type(cpt))
if isinstance(cpt, dict):
    print("keys:", list(cpt.keys()))
elif isinstance(cpt, list):
    print("len:", len(cpt))
    print(json.dumps(cpt[:2], ensure_ascii=False, indent=2))

sc = load('data/smallcap_risk_screen.json')
print("=== smallcap_risk_screen ===")
print("type:", type(sc))
if isinstance(sc, dict):
    print("keys:", list(sc.keys()))
elif isinstance(sc, list):
    print("len:", len(sc))
