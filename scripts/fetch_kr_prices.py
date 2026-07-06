#!/usr/bin/env python3
"""
한국주식 실시간가 수집 → Firebase Firestore 저장
GitHub Actions에서 KR 장 중(09:00-15:30 KST) 10분마다 실행

필요 GitHub Secrets:
  FIREBASE_SERVICE_ACCOUNT  — Firebase 서비스 계정 JSON (문자열)

KIS API는 모의투자 토큰으로 가격 조회 가능 (선택).
기본은 Yahoo Finance 사용 (CORS 없이 GitHub Actions 환경에서 직접 호출).
"""

import os, json, time, sys
from datetime import datetime, timezone
import urllib.request

# ── Firebase 초기화
def init_firebase():
    import firebase_admin
    from firebase_admin import credentials, firestore

    sa_raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")
    if not sa_raw:
        print("ERROR: FIREBASE_SERVICE_ACCOUNT secret 없음", file=sys.stderr)
        sys.exit(1)

    sa_json = json.loads(sa_raw)
    cred = credentials.Certificate(sa_json)
    firebase_admin.initialize_app(cred)
    return firestore.client()


# ── Yahoo Finance v8/chart 단건 조회
def fetch_yahoo_price(symbol: str) -> dict | None:
    """symbol: '005930.KS' 형식"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev  = meta.get("chartPreviousClose") or meta.get("regularMarketPreviousClose") or price
        chg   = price - prev
        chgPct = (chg / prev * 100) if prev else 0
        vol   = meta.get("regularMarketVolume", 0)
        return {
            "price":     int(price),
            "change":    int(chg),
            "changePct": round(chgPct, 2),
            "volume":    vol,
            "high52":    int(meta.get("fiftyTwoWeekHigh", 0)),
            "low52":     int(meta.get("fiftyTwoWeekLow", 0)),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"  WARN {symbol}: {e}", file=sys.stderr)
        return None


# ── KIS API 가격 조회 (선택 — 모의투자 App Key 보유 시)
def fetch_kis_price(code: str, token: str, app_key: str, app_secret: str,
                    base_url: str) -> dict | None:
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "Authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01010100",
        "custtype": "P",
        "Content-Type": "application/json; charset=utf-8",
    }
    params = f"FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD={code}"
    try:
        req = urllib.request.Request(
            f"{url}?{params}", headers=headers, method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read()).get("output", {})
        price = int(d.get("stck_prpr", 0))
        if price == 0:
            return None
        prev  = int(d.get("stck_sdpr", price))
        chg   = int(d.get("prdy_vrss", 0))
        return {
            "price":     price,
            "change":    chg,
            "changePct": round(float(d.get("prdy_ctrt", 0)), 2),
            "volume":    int(d.get("acml_vol", 0)),
            "high52":    int(d.get("stck_hgpr", 0)),
            "low52":     int(d.get("stck_lwpr", 0)),
            "source":    "KIS",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"  WARN KIS {code}: {e}", file=sys.stderr)
        return None


def get_kis_token(app_key: str, app_secret: str, base_url: str) -> str | None:
    url = f"{base_url}/oauth2/tokenP"
    body = json.dumps({
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret,
    }).encode()
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("access_token")
    except Exception as e:
        print(f"  WARN KIS 토큰: {e}", file=sys.stderr)
        return None


# ── 종목 목록 (code, yahoo_symbol, name)
KR_STOCKS = [
    # KOSPI
    ("005930", "005930.KS", "삼성전자"),
    ("000660", "000660.KS", "SK하이닉스"),
    ("005380", "005380.KS", "현대차"),
    ("000270", "000270.KS", "기아"),
    ("051910", "051910.KS", "LG화학"),
    ("006400", "006400.KS", "삼성SDI"),
    ("373220", "373220.KS", "LG에너지솔루션"),
    ("068270", "068270.KS", "셀트리온"),
    ("207940", "207940.KS", "삼성바이오로직스"),
    ("105560", "105560.KS", "KB금융"),
    ("055550", "055550.KS", "신한지주"),
    ("086790", "086790.KS", "하나금융지주"),
    ("012330", "012330.KS", "현대모비스"),
    ("028260", "028260.KS", "삼성물산"),
    ("096770", "096770.KS", "SK이노베이션"),
    ("010950", "010950.KS", "S-Oil"),
    ("015760", "015760.KS", "한국전력"),
    ("042700", "042700.KS", "한미반도체"),
    ("000990", "000990.KS", "DB하이텍"),
    ("064350", "064350.KS", "현대로템"),
    # KOSDAQ
    ("247540", "247540.KQ", "에코프로비엠"),
    ("086520", "086520.KQ", "에코프로"),
    ("323410", "323410.KQ", "카카오뱅크"),
    ("259960", "259960.KQ", "크래프톤"),
    ("041510", "041510.KQ", "SM엔터"),
    ("352820", "352820.KQ", "하이브"),
    ("035420", "035420.KS", "NAVER"),
    ("035720", "035720.KS", "카카오"),
]


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] KR 주식 가격 수집 시작...")

    # ── KIS 설정 (있으면 우선 사용)
    KIS_APP_KEY    = os.environ.get("KIS_APP_KEY", "")
    KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET", "")
    KIS_BASE       = "https://openapivts.koreainvestment.com:29443"  # 모의
    kis_token      = None
    if KIS_APP_KEY and KIS_APP_SECRET:
        kis_token = get_kis_token(KIS_APP_KEY, KIS_APP_SECRET, KIS_BASE)
        print(f"  KIS 토큰 {'발급 완료' if kis_token else '실패 — Yahoo 대체'}")

    # ── 가격 수집
    prices = {}
    for code, yahoo_sym, name in KR_STOCKS:
        data = None
        # KIS 우선 시도
        if kis_token:
            data = fetch_kis_price(code, kis_token, KIS_APP_KEY, KIS_APP_SECRET, KIS_BASE)
        # Yahoo Finance 폴백
        if not data:
            data = fetch_yahoo_price(yahoo_sym)
            if data:
                data["source"] = "Yahoo"
        if data:
            prices[code] = {**data, "name": name}
            src = data.get("source", "Yahoo")
            print(f"  {code} {name}: {data['price']:,}원 ({data['changePct']:+.2f}%) [{src}]")
        else:
            print(f"  {code} {name}: 조회 실패")
        time.sleep(0.2)

    if not prices:
        print("ERROR: 가격 데이터 없음 — Firebase 저장 스킵", file=sys.stderr)
        sys.exit(1)

    # ── Firebase 저장
    print(f"\nFirebase 저장 중... ({len(prices)}개 종목)")
    db = init_firebase()
    from firebase_admin import firestore as fs_module
    db.collection("radar").document("kr_prices").set({
        "prices": prices,
        "count":  len(prices),
        "updatedAt": fs_module.SERVER_TIMESTAMP,
        "updatedAtStr": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    })
    print(f"✅ Firebase 저장 완료 — {len(prices)}개 종목")


if __name__ == "__main__":
    main()
