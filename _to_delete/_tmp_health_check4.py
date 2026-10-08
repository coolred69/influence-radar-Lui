import json, sys

def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)

out = open('_tmp_health_out.txt', 'w', encoding='utf-8')

def P(*a):
    print(*a, file=out)

d = load('data/overfit_report.json')
P("=== overfit_report ===")
P(json.dumps(d, ensure_ascii=False, indent=2))

cpt = load('data/combined_probability_table.json')
P("=== combined_probability_table type ===", type(cpt))
if isinstance(cpt, dict):
    P("keys:", list(cpt.keys()))
    P(json.dumps(cpt, ensure_ascii=False, indent=2)[:3000])
elif isinstance(cpt, list):
    P("len:", len(cpt))
    P(json.dumps(cpt[:3], ensure_ascii=False, indent=2))

sc = load('data/smallcap_risk_screen.json')
P("=== smallcap_risk_screen ===")
P("keys:", list(sc.keys()) if isinstance(sc, dict) else type(sc))
P(json.dumps(sc, ensure_ascii=False, indent=2)[:2500])

fk = load('data/fundamental_kr.json')
P("=== fundamental_kr ===")
P("type:", type(fk))
if isinstance(fk, list):
    P("len:", len(fk))
    P(json.dumps(fk[:2], ensure_ascii=False, indent=2))
elif isinstance(fk, dict):
    P("keys:", list(fk.keys()))
    P(json.dumps(fk, ensure_ascii=False, indent=2)[:1500])

out.close()
print("DONE")
