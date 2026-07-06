#!/usr/bin/env python3
"""
한국투자증권 통합 MCP 서버 v2.0
- 한국 주식 실시간 시세 / 매매
- 미국 주식 실시간 시세 / 매매 (NASDAQ, NYSE, AMEX)
- 매매 기록 DB (SQLite)
- 성과 분석 / 학습 루프
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ── 환경 설정 ────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

APP_KEY    = os.getenv("KIS_APP_KEY", "")
APP_SECRET = os.getenv("KIS_APP_SECRET", "")
ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "")
BASE_URL   = "https://openapivts.koreainvestment.com:29443"  # 모의투자
DB_PATH    = Path(__file__).parent / "trades.db"

mcp = FastMCP("KIS 한국투자증권 통합 (한국+미국)")

# ── 토큰 캐시 ────────────────────────────────────────────────
_token_cache: dict = {"token": None, "expires": None}


# ══════════════════════════════════════════════════════════════
# 내부 헬퍼
# ══════════════════════════════════════════════════════════════

async def _get_token() -> str:
    now = datetime.now()
    if _token_cache["token"] and _token_cache["expires"] and _token_cache["expires"] > now:
        return _token_cache["token"]
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.post(
            f"{BASE_URL}/oauth2/tokenP",
            headers={"content-type": "application/json"},
            json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET},
        )
        data = r.json()
        if "access_token" not in data:
            raise RuntimeError(f"토큰 발급 실패: {data}")
        _token_cache["token"] = data["access_token"]
        _token_cache["expires"] = now + timedelta(hours=23)
        return _token_cache["token"]


async def _hashkey(body: dict) -> str:
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.post(
            f"{BASE_URL}/uapi/hashkey",
            headers={"content-type": "application/json", "appkey": APP_KEY, "appsecret": APP_SECRET},
            json=body,
        )
        return r.json().get("HASH", "")


def _fmt(n) -> str:
    try:
        return f"{int(float(n)):,}"
    except Exception:
        return str(n)


def _cano() -> str:
    if not ACCOUNT_NO:
        raise RuntimeError(".env 의 KIS_ACCOUNT_NO 를 설정해주세요.")
    return ACCOUNT_NO


# ══════════════════════════════════════════════════════════════
# DB 초기화 (학습 루프용 SQLite)
# ══════════════════════════════════════════════════════════════

def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            market      TEXT,        -- KR / US
            stock_code  TEXT,
            stock_name  TEXT,
            action      TEXT,        -- buy / sell
            entry_price REAL,
            quantity    INTEGER,
            entry_date  TEXT,
            exit_price  REAL,
            exit_date   TEXT,
            pnl         REAL,        -- 손익 (원/달러)
            pnl_pct     REAL,        -- 수익률 %
            status      TEXT,        -- open / closed
            reasoning   TEXT,        -- Claude 의 매수 근거
            confidence  INTEGER,     -- 확신도 1~10
            outcome_note TEXT        -- 결과 메모
        )
    """)
    con.commit()
    con.close()

_init_db()


# ══════════════════════════════════════════════════════════════
# 한국 주식
# ══════════════════════════════════════════════════════════════

@mcp.tool()
async def get_kr_stock_price(stock_code: str) -> str:
    """
    한국 주식 현재가 조회.
    stock_code: 종목코드 6자리 (예: 005930=삼성전자, 000660=SK하이닉스)
    """
    token = await _get_token()
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.get(
            f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET,
                "tr_id": "FHKST01010100", "custtype": "P",
            },
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code},
        )
    o = r.json().get("output", {})
    return json.dumps({
        "종목명":       o.get("hts_kor_isnm", ""),
        "현재가":       f"₩{_fmt(o.get('stck_prpr', 0))}",
        "전일대비":     o.get("prdy_vrss", ""),
        "등락률":       f"{o.get('prdy_ctrt', '')}%",
        "거래량":       _fmt(o.get("acml_vol", 0)),
        "시가":         f"₩{_fmt(o.get('stck_oprc', 0))}",
        "고가":         f"₩{_fmt(o.get('stck_hgpr', 0))}",
        "저가":         f"₩{_fmt(o.get('stck_lwpr', 0))}",
        "52주고가":     f"₩{_fmt(o.get('d250_hgpr', 0))}",
        "52주저가":     f"₩{_fmt(o.get('d250_lwpr', 0))}",
        "시가총액(억)": o.get("hts_avls", ""),
        "PER": o.get("per", ""), "PBR": o.get("pbr", ""), "EPS": o.get("eps", ""),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_kr_stock_history(stock_code: str, period: str = "D") -> str:
    """
    한국 주식 봉 데이터 (최근 30개).
    period: D=일봉, W=주봉, M=월봉
    """
    token = await _get_token()
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.get(
            f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET,
                "tr_id": "FHKST01010400", "custtype": "P",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code,
                "FID_PERIOD_DIV_CODE": period, "FID_ORG_ADJ_PRC": "0",
            },
        )
    rows = [
        {"날짜": o.get("stck_bsop_date"), "시가": o.get("stck_oprc"),
         "고가": o.get("stck_hgpr"), "저가": o.get("stck_lwpr"),
         "종가": o.get("stck_clpr"), "거래량": o.get("acml_vol"), "등락률": o.get("prdy_ctrt")}
        for o in r.json().get("output2", [])[:30]
    ]
    return json.dumps(rows, ensure_ascii=False, indent=2)


@mcp.tool()
async def place_kr_order(
    stock_code: str, action: str, quantity: int, price: int = 0,
) -> str:
    """
    한국 주식 모의투자 주문.
    action: 'buy' / 'sell' | price: 0=시장가
    """
    token = await _get_token()
    cano  = _cano()
    body  = {
        "CANO": cano, "ACNT_PRDT_CD": "01", "PDNO": stock_code,
        "ORD_DVSN": "01" if price == 0 else "00",
        "ORD_QTY": str(quantity), "ORD_UNPR": str(price),
    }
    hashkey = await _hashkey(body)
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.post(
            f"{BASE_URL}/uapi/domestic-stock/v1/trading/order-cash",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET,
                "tr_id": "VTTC0802U" if action == "buy" else "VTTC0801U",
                "custtype": "P", "hashkey": hashkey, "content-type": "application/json",
            },
            json=body,
        )
    return json.dumps(r.json(), ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════
# 미국 주식
# ══════════════════════════════════════════════════════════════

@mcp.tool()
async def get_us_stock_price(symbol: str, exchange: str = "NASD") -> str:
    """
    미국 주식 현재가 조회.
    symbol: 티커 (AAPL, NVDA, TSLA 등)
    exchange: NASD=나스닥, NYSE=뉴욕, AMEX=아멕스
    """
    token = await _get_token()
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.get(
            f"{BASE_URL}/uapi/overseas-price/v1/quotations/price",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET,
                "tr_id": "HHDFS00000300", "custtype": "P",
            },
            params={"AUTH": "", "EXCD": exchange, "SYMB": symbol},
        )
    o = r.json().get("output", {})
    return json.dumps({
        "종목":     symbol,
        "거래소":   exchange,
        "현재가":   f"${o.get('last', '')}",
        "전일대비": o.get("diff", ""),
        "등락률":   f"{o.get('rate', '')}%",
        "시가":     f"${o.get('open', '')}",
        "고가":     f"${o.get('high', '')}",
        "저가":     f"${o.get('low', '')}",
        "거래량":   _fmt(o.get("tvol", 0)),
        "52주고가": f"${o.get('h52p', '')}",
        "52주저가": f"${o.get('l52p', '')}",
        "PER":      o.get("per", ""),
        "EPS":      o.get("eps", ""),
        "시가총액": o.get("valx", ""),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_us_stock_history(symbol: str, exchange: str = "NASD", period: str = "0") -> str:
    """
    미국 주식 봉 데이터 (최근 30개).
    exchange: NASD/NYSE/AMEX | period: 0=일봉, 1=주봉, 2=월봉
    """
    token = await _get_token()
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.get(
            f"{BASE_URL}/uapi/overseas-price/v1/quotations/dailyprice",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET,
                "tr_id": "HHDFS76240000", "custtype": "P",
            },
            params={"AUTH": "", "EXCD": exchange, "SYMB": symbol,
                    "GUBN": period, "BYMD": "", "MODP": "0"},
        )
    rows = [
        {"날짜": o.get("xymd"), "시가": o.get("open"), "고가": o.get("high"),
         "저가": o.get("low"), "종가": o.get("clos"), "거래량": o.get("tvol"), "등락률": o.get("rate")}
        for o in r.json().get("output2", [])[:30]
    ]
    return json.dumps(rows, ensure_ascii=False, indent=2)


@mcp.tool()
async def place_us_order(
    symbol: str, action: str, quantity: int, price: float = 0,
    exchange: str = "NASD",
) -> str:
    """
    미국 주식 모의투자 주문.
    symbol: 티커 | action: 'buy'/'sell' | price: 0=시장가 | exchange: NASD/NYSE/AMEX
    """
    token = await _get_token()
    cano  = _cano()
    body  = {
        "CANO": cano, "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": exchange, "PDNO": symbol,
        "ORD_DVSN": "00", "ORD_QTY": str(quantity),
        "OVRS_ORD_UNPR": str(price),
    }
    hashkey = await _hashkey(body)
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.post(
            f"{BASE_URL}/uapi/overseas-stock/v1/trading/order",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET,
                "tr_id": "VTTT1002U" if action == "buy" else "VTTT1006U",
                "custtype": "P", "hashkey": hashkey, "content-type": "application/json",
            },
            json=body,
        )
    return json.dumps(r.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def get_us_account_balance() -> str:
    """미국 주식 모의투자 계좌 잔고 조회."""
    token = await _get_token()
    cano  = _cano()
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.get(
            f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET,
                "tr_id": "VTTS3012R", "custtype": "P",
            },
            params={
                "CANO": cano, "ACNT_PRDT_CD": "01",
                "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
            },
        )
    return json.dumps(r.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def get_kr_account_balance() -> str:
    """한국 주식 모의투자 계좌 잔고 조회."""
    token = await _get_token()
    cano  = _cano()
    async with httpx.AsyncClient(verify=False) as c:
        r = await c.get(
            f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET,
                "tr_id": "VTTC8434R", "custtype": "P",
            },
            params={
                "CANO": cano, "ACNT_PRDT_CD": "01", "AFHR_FLPR_YN": "N",
                "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
        )
    return json.dumps(r.json(), ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════
# 학습 루프 — 매매 기록 & 성과 분석
# ══════════════════════════════════════════════════════════════

@mcp.tool()
def log_trade_entry(
    market: str, stock_code: str, stock_name: str,
    action: str, entry_price: float, quantity: int,
    reasoning: str, confidence: int,
) -> str:
    """
    매매 추천 기록 저장 (매수/매도 진입 시).
    market: 'KR'/'US' | confidence: 확신도 1~10
    반환값: trade_id (결과 기록 시 사용)
    """
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(
        """INSERT INTO trades
           (market, stock_code, stock_name, action, entry_price, quantity,
            entry_date, status, reasoning, confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (market, stock_code, stock_name, action, entry_price, quantity,
         datetime.now().isoformat(), "open", reasoning, confidence),
    )
    trade_id = cur.lastrowid
    con.commit(); con.close()
    return json.dumps({"trade_id": trade_id, "status": "기록 완료"}, ensure_ascii=False)


@mcp.tool()
def log_trade_exit(trade_id: int, exit_price: float, outcome_note: str = "") -> str:
    """
    매매 결과 기록 (청산 시).
    trade_id: log_trade_entry 에서 받은 ID
    exit_price: 청산 가격
    """
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT action, entry_price, quantity FROM trades WHERE id=?", (trade_id,)).fetchone()
    if not row:
        con.close()
        return f"trade_id {trade_id} 를 찾을 수 없습니다."
    action, entry_price, quantity = row
    pnl     = (exit_price - entry_price) * quantity if action == "buy" else (entry_price - exit_price) * quantity
    pnl_pct = ((exit_price - entry_price) / entry_price * 100) if action == "buy" \
               else ((entry_price - exit_price) / entry_price * 100)
    con.execute(
        "UPDATE trades SET exit_price=?, exit_date=?, pnl=?, pnl_pct=?, status='closed', outcome_note=? WHERE id=?",
        (exit_price, datetime.now().isoformat(), pnl, pnl_pct, outcome_note, trade_id),
    )
    con.commit(); con.close()
    result = "✅ 수익" if pnl > 0 else "❌ 손실"
    return json.dumps({
        "trade_id": trade_id, "결과": result,
        "손익": round(pnl, 2), "수익률": f"{round(pnl_pct, 2)}%",
    }, ensure_ascii=False)


@mcp.tool()
def get_performance_report(market: str = "ALL") -> str:
    """
    성과 분석 리포트 (학습 루프 피드백).
    market: 'KR' / 'US' / 'ALL'
    """
    con = sqlite3.connect(DB_PATH)
    where = "" if market == "ALL" else f"WHERE market='{market}'"
    rows  = con.execute(f"SELECT * FROM trades {where} ORDER BY entry_date DESC").fetchall()
    con.close()
    if not rows:
        return "기록된 매매가 없습니다."

    cols   = ["id","market","stock_code","stock_name","action","entry_price","quantity",
              "entry_date","exit_price","exit_date","pnl","pnl_pct","status","reasoning","confidence","outcome_note"]
    closed = [dict(zip(cols, r)) for r in rows if r[12] == "closed"]
    open_  = [dict(zip(cols, r)) for r in rows if r[12] == "open"]

    if closed:
        wins     = [t for t in closed if t["pnl"] and t["pnl"] > 0]
        losses   = [t for t in closed if t["pnl"] and t["pnl"] <= 0]
        win_rate = len(wins) / len(closed) * 100
        avg_ret  = sum(t["pnl_pct"] for t in closed if t["pnl_pct"]) / len(closed)
        total_pnl= sum(t["pnl"] for t in closed if t["pnl"])
        best     = max(closed, key=lambda x: x["pnl_pct"] or 0)
        worst    = min(closed, key=lambda x: x["pnl_pct"] or 0)

        # 확신도별 승률
        conf_analysis = {}
        for t in closed:
            c = t["confidence"] or 0
            bucket = f"{(c//3)*3+1}~{(c//3)*3+3}"
            if bucket not in conf_analysis:
                conf_analysis[bucket] = {"total": 0, "wins": 0}
            conf_analysis[bucket]["total"] += 1
            if t["pnl"] and t["pnl"] > 0:
                conf_analysis[bucket]["wins"] += 1
        for k in conf_analysis:
            d = conf_analysis[k]
            d["win_rate"] = f"{d['wins']/d['total']*100:.1f}%"

        summary = {
            "분석대상": market,
            "전체거래": len(closed),
            "오픈포지션": len(open_),
            "승률": f"{win_rate:.1f}%",
            "평균수익률": f"{avg_ret:.2f}%",
            "총손익": round(total_pnl, 2),
            "최고수익": f"{best['stock_name']}({best['stock_code']}) {best['pnl_pct']:.2f}%",
            "최대손실": f"{worst['stock_name']}({worst['stock_code']}) {worst['pnl_pct']:.2f}%",
            "확신도별승률": conf_analysis,
            "최근5거래": [
                {"종목": t["stock_name"], "행동": t["action"],
                 "수익률": f"{t['pnl_pct']:.2f}%" if t["pnl_pct"] else "-",
                 "근거요약": (t["reasoning"] or "")[:80]}
                for t in closed[:5]
            ],
        }
    else:
        summary = {"메시지": "청산 완료 거래 없음 (오픈 포지션만 존재)", "오픈포지션": len(open_)}

    return json.dumps(summary, ensure_ascii=False, indent=2)


@mcp.tool()
def get_open_positions(market: str = "ALL") -> str:
    """현재 오픈 포지션 (청산 전 보유 종목) 조회."""
    con = sqlite3.connect(DB_PATH)
    where = "WHERE status='open'" if market == "ALL" else f"WHERE status='open' AND market='{market}'"
    rows  = con.execute(f"SELECT id,market,stock_code,stock_name,action,entry_price,quantity,entry_date,reasoning FROM trades {where}").fetchall()
    con.close()
    result = [
        {"id": r[0], "시장": r[1], "코드": r[2], "종목": r[3], "포지션": r[4],
         "진입가": r[5], "수량": r[6], "진입일": r[7], "근거": (r[8] or "")[:100]}
        for r in rows
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_trade_history(limit: int = 20) -> str:
    """전체 매매 이력 조회 (최근 N건)."""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT id,market,stock_code,stock_name,action,entry_price,exit_price,pnl_pct,status,entry_date FROM trades ORDER BY entry_date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    con.close()
    result = [
        {"id": r[0], "시장": r[1], "코드": r[2], "종목": r[3], "포지션": r[4],
         "진입가": r[5], "청산가": r[6] or "-",
         "수익률": f"{r[7]:.2f}%" if r[7] else "-",
         "상태": r[8], "날짜": r[9]}
        for r in rows
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def search_stock(query: str) -> str:
    """종목명/티커로 코드 검색."""
    kr_stocks = {
        "삼성전자": "005930", "삼성전자우": "005935", "SK하이닉스": "000660",
        "LG에너지솔루션": "373220", "삼성바이오로직스": "207940", "현대차": "005380",
        "셀트리온": "068270", "기아": "000270", "NAVER": "035420", "카카오": "035720",
        "LG화학": "051910", "POSCO홀딩스": "005490", "삼성SDI": "006400",
        "현대모비스": "012330", "KB금융": "105560", "신한지주": "055550",
        "하나금융지주": "086790", "삼성물산": "028260", "SK텔레콤": "017670",
        "한미반도체": "042700", "에코프로비엠": "247540", "에코프로": "086520",
        "LG전자": "066570", "크래프톤": "259960", "카카오뱅크": "323410",
    }
    us_stocks = {
        "NVDA": "NASD", "AAPL": "NASD", "MSFT": "NASD", "AMZN": "NASD",
        "GOOGL": "NASD", "META": "NASD", "TSLA": "NASD", "AMD": "NASD",
        "INTC": "NASD", "AVGO": "NASD", "TSM": "NYSE", "ASML": "NASD",
        "MU": "NASD", "QCOM": "NASD", "AMAT": "NASD", "LRCX": "NASD",
        "KLAC": "NASD", "JPM": "NYSE", "BAC": "NYSE", "GS": "NYSE",
    }
    q = query.upper()
    kr_hits = {k: {"코드": v, "시장": "KR"} for k, v in kr_stocks.items() if query in k}
    us_hits = {k: {"거래소": v, "시장": "US"} for k, v in us_stocks.items() if q in k}
    result  = {"한국주식": kr_hits, "미국주식": us_hits}
    if not kr_hits and not us_hits:
        return f"'{query}' 검색 결과 없음."
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
