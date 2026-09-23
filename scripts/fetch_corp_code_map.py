"""
DART corp_code(8자리 고유번호) ↔ 종목코드 매핑 캐시 생성.
DART는 종목코드로 직접 조회를 지원하지 않아 corp_code가 반드시 필요함.
corpCode.xml 전체(3.6MB)를 매번 받는 건 비효율적이므로 1회 생성 후 캐시.
워치리스트 변경 시에만 재실행.
"""
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import io
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DART_KEY = os.environ.get("DART_API_KEY", "")
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

WATCHLIST_TICKERS = [
    "005930", "000660", "005380", "000270", "373220",
    "035720", "035420", "096770", "207940", "051910",
]


def main():
    if not DART_KEY:
        raise SystemExit("DART_API_KEY 없음 — .env 확인 필요")

    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={DART_KEY}"
    with urllib.request.urlopen(url, timeout=120) as resp:
        zip_bytes = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    root = ET.fromstring(xml_bytes)
    found = {}
    for corp in root.findall("list"):
        sc = (corp.findtext("stock_code") or "").strip()
        if sc in WATCHLIST_TICKERS:
            found[sc] = {
                "corp_code": corp.findtext("corp_code").strip(),
                "corp_name": corp.findtext("corp_name").strip(),
            }

    missing = set(WATCHLIST_TICKERS) - set(found)
    if missing:
        print(f"[경고] 매핑 실패 종목: {missing}")

    out_path = DATA_DIR / "dart_corp_map_kr.json"
    out_path.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {out_path} ({len(found)}/{len(WATCHLIST_TICKERS)}종목 매칭)")


if __name__ == "__main__":
    main()
