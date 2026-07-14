#!/usr/bin/env python3
"""
Influence Radar — 실데이터 훈련셋 빌더 v2
────────────────────────────────────────
200+ 인플루언서 이벤트 + yfinance OHLCV
→ 12개 기술지표 계산 (갭, 52주 위치, 사전모멘텀, ATR 추가)
→ 10일 후 수익 결과 판정
→ data/training_data.json 저장
"""

import json, os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

OUTPUT_PATH  = "data/training_data.json"
HOLD_DAYS    = 10
TARGET_RET   = 0.03

# ──────────────────────────────────────────────────────────────
# 이벤트 목록 (날짜, 인물, 심볼, 이벤트, 감정, 섹터, 검증수)
# ──────────────────────────────────────────────────────────────
EVENTS = [
    # ═══ 🇰🇷 한국 이재용 (삼성전자/SK하이닉스) ═══
    ("2023-06-12", "이재용",   "005930.KS", "AI반도체 로드맵",    "positive", "KR_SEMICON", 4),
    ("2023-08-21", "이재용",   "005930.KS", "실적개선 발표",       "positive", "KR_SEMICON", 4),
    ("2023-10-26", "이재용",   "005930.KS", "3Q실적서프라이즈",    "positive", "KR_SEMICON", 5),
    ("2024-01-15", "이재용",   "005930.KS", "실적발표예고",        "positive", "KR_SEMICON", 4),
    ("2024-03-20", "이재용",   "005930.KS", "AI칩 투자발표",       "positive", "KR_SEMICON", 5),
    ("2024-05-10", "이재용",   "005930.KS", "글로벌파트너십",      "positive", "KR_SEMICON", 3),
    ("2024-07-08", "이재용",   "000660.KS", "HBM 공급확대",        "positive", "KR_SEMICON", 4),
    ("2024-09-12", "이재용",   "005930.KS", "실적부진 우려",       "negative", "KR_SEMICON", 5),
    ("2024-11-05", "이재용",   "005930.KS", "파운드리 전략",       "positive", "KR_SEMICON", 3),
    ("2025-01-20", "이재용",   "005930.KS", "AI메모리 수요증가",   "positive", "KR_SEMICON", 5),
    ("2025-03-15", "이재용",   "000660.KS", "HBM4 개발완료",       "positive", "KR_SEMICON", 4),
    ("2025-05-08", "이재용",   "005930.KS", "2분기 실적가이던스",  "positive", "KR_SEMICON", 4),
    ("2025-07-31", "이재용",   "005930.KS", "2Q25 실적부진(영업이익 -56%YoY)", "negative", "KR_SEMICON", 4),
    ("2025-10-30", "이재용",   "005930.KS", "3Q25 실적급증(영업이익 +159%QoQ)", "positive", "KR_SEMICON", 5),

    # ═══ 🇰🇷 정의선 (현대차/기아) ═══
    ("2023-05-25", "정의선",   "005380.KS", "E-GMP 플랫폼 확대",  "positive", "KR_AUTO", 3),
    ("2023-07-26", "정의선",   "005380.KS", "2Q 실적호조",         "positive", "KR_AUTO", 4),
    ("2023-10-19", "정의선",   "000270.KS", "전기차 보조금 확대",  "positive", "KR_AUTO", 3),
    ("2024-02-14", "정의선",   "005380.KS", "전기차 판매목표",     "positive", "KR_AUTO", 4),
    ("2024-04-22", "정의선",   "000270.KS", "북미시장 확대",       "positive", "KR_AUTO", 3),
    ("2024-06-18", "정의선",   "005380.KS", "배터리내재화",        "positive", "KR_BATTERY", 4),
    ("2024-08-27", "정의선",   "000270.KS", "전기차 수요둔화",     "negative", "KR_AUTO", 5),
    ("2024-10-14", "정의선",   "005380.KS", "로보틱스투자",        "positive", "KR_AUTO", 3),
    ("2025-02-10", "정의선",   "000270.KS", "하이브리드전략",      "positive", "KR_AUTO", 4),
    ("2025-04-17", "정의선",   "005380.KS", "1Q 실적발표",         "positive", "KR_AUTO", 4),
    ("2025-07-24", "정의선",   "005380.KS", "2Q25 실적부진(관세영향 영업이익 -15.8%)", "negative", "KR_AUTO", 4),
    ("2025-10-30", "정의선",   "005380.KS", "3Q25 관세영향 본격화(영업이익 -29.2%)", "negative", "KR_AUTO", 4),

    # ═══ 🇰🇷 최태원 (SK하이닉스/SK이노) ═══
    ("2023-07-26", "최태원",   "000660.KS", "HBM3 양산 시작",      "positive", "KR_SEMICON", 5),
    ("2023-11-08", "최태원",   "000660.KS", "엔비디아 HBM 독점",   "positive", "KR_SEMICON", 6),
    ("2024-03-07", "최태원",   "000660.KS", "AI반도체 수혜",       "positive", "KR_SEMICON", 5),
    ("2024-06-03", "최태원",   "096770.KS", "배터리사업재편",      "positive", "KR_BATTERY", 3),
    ("2024-09-23", "최태원",   "000660.KS", "HBM 점유율확대",      "positive", "KR_SEMICON", 5),
    ("2025-01-08", "최태원",   "000660.KS", "엔비디아 공급망",     "positive", "KR_SEMICON", 5),
    ("2025-04-24", "최태원",   "000660.KS", "1Q 사상최대 실적",    "positive", "KR_SEMICON", 6),
    ("2025-07-24", "최태원",   "000660.KS", "2Q25 실적호조(영업이익 9.2조)", "positive", "KR_SEMICON", 6),
    ("2025-10-29", "최태원",   "000660.KS", "3Q25 사상최대실적(영업이익 11.4조)", "positive", "KR_SEMICON", 6),

    # ═══ 🇰🇷 이재명 (정책 수혜주) ═══
    ("2023-09-14", "이재명",   "373220.KS", "배터리 보조금 공약",  "positive", "KR_BATTERY", 4),
    ("2024-04-11", "이재명",   "373220.KS", "배터리산업육성",      "positive", "KR_BATTERY", 4),
    ("2024-07-15", "이재명",   "005380.KS", "전기차 보조금확대",   "positive", "KR_AUTO", 3),
    ("2024-10-28", "이재명",   "000660.KS", "반도체 국가지원",     "positive", "KR_SEMICON", 4),
    ("2025-03-05", "이재명",   "373220.KS", "K배터리 정책",        "positive", "KR_BATTERY", 5),
    ("2025-05-12", "이재명",   "005930.KS", "반도체 세제지원",     "positive", "KR_SEMICON", 4),

    # ═══ 🇰🇷 구광모 (LG에너지솔루션/LG전자) ═══
    ("2023-08-08", "구광모",   "373220.KS", "GM 배터리 증설",      "positive", "KR_BATTERY", 4),
    ("2023-11-07", "구광모",   "373220.KS", "북미 생산 확대",      "positive", "KR_BATTERY", 4),
    ("2024-02-06", "구광모",   "373220.KS", "원통형배터리 수주",   "positive", "KR_BATTERY", 3),
    ("2024-05-09", "구광모",   "373220.KS", "2Q 실적 전망",        "neutral",  "KR_BATTERY", 3),
    ("2024-09-03", "구광모",   "373220.KS", "전기차 수요회복",     "positive", "KR_BATTERY", 4),
    ("2025-02-06", "구광모",   "373220.KS", "전고체배터리 투자",   "positive", "KR_BATTERY", 5),

    # ═══ 🇰🇷 김범수 (카카오) ═══
    ("2023-06-15", "김범수",   "035720.KS", "AI 서비스 출시",      "positive", "KR_TECH", 3),
    ("2023-09-21", "김범수",   "035720.KS", "수사 관련 악재",      "negative", "KR_TECH", 4),
    ("2024-01-11", "김범수",   "035720.KS", "구조조정 발표",       "negative", "KR_TECH", 4),
    ("2024-07-22", "김범수",   "035720.KS", "AI 카카오 재도전",    "positive", "KR_TECH", 3),

    # ═══ 🇰🇷 최수연 (네이버) ═══
    ("2023-10-24", "최수연",   "035420.KS", "라인야후 재편",       "negative", "KR_TECH", 4),
    ("2024-02-27", "최수연",   "035420.KS", "라인 지분 매각압박",  "negative", "KR_TECH", 5),
    ("2024-06-04", "최수연",   "035420.KS", "HyperCLOVA 출시",    "positive", "KR_TECH", 3),
    ("2025-01-16", "최수연",   "035420.KS", "AI 검색 강화",        "positive", "KR_TECH", 4),

    # ═══ 🇺🇸 Jensen Huang (NVIDIA) ═══
    ("2023-02-22", "Jensen Huang", "NVDA", "ChatGPT 인프라 언급", "positive", "AI/GPU", 6),
    ("2023-05-24", "Jensen Huang", "NVDA", "Q1 실적 폭발적 성장", "positive", "AI/GPU", 6),
    ("2023-08-23", "Jensen Huang", "NVDA", "Q2 실적 +110% 어닝",  "positive", "AI/GPU", 6),
    ("2023-11-21", "Jensen Huang", "NVDA", "Q3 실적서프라이즈",   "positive", "AI/GPU", 6),
    ("2024-01-08", "Jensen Huang", "NVDA", "CES기조연설 AI칩",    "positive", "AI/GPU", 6),
    ("2024-03-18", "Jensen Huang", "NVDA", "GTC H200 발표",       "positive", "AI/GPU", 6),
    ("2024-05-22", "Jensen Huang", "NVDA", "Q1FY25 실적서프라이즈","positive","AI/GPU", 6),
    ("2024-08-28", "Jensen Huang", "NVDA", "Blackwell 출하지연",  "negative", "AI/GPU", 5),
    ("2024-11-20", "Jensen Huang", "NVDA", "FQ3 실적발표",        "positive", "AI/GPU", 6),
    ("2025-01-06", "Jensen Huang", "NVDA", "CES2025 GB200",       "positive", "AI/GPU", 6),
    ("2025-03-17", "Jensen Huang", "NVDA", "GTC2025 Blackwell",   "positive", "AI/GPU", 6),
    ("2025-05-28", "Jensen Huang", "NVDA", "FQ1FY26 실적발표",    "positive", "AI/GPU", 6),
    ("2025-08-27", "Jensen Huang", "NVDA", "FQ2FY26 실적서프라이즈(네트워킹 98%↑)", "positive", "AI/GPU", 6),
    ("2025-11-19", "Jensen Huang", "NVDA", "FQ3FY26 사상최대매출 570억 서프라이즈", "positive", "AI/GPU", 6),

    # ═══ 🇺🇸 Elon Musk (Tesla/X) ═══
    ("2023-04-19", "Elon Musk", "TSLA", "가격인하 마진압박",    "negative", "EV/Auto", 5),
    ("2023-07-19", "Elon Musk", "TSLA", "Q2 실적서프라이즈",    "positive", "EV/Auto", 5),
    ("2023-10-18", "Elon Musk", "TSLA", "Q3 실망 이익감소",     "negative", "EV/Auto", 5),
    ("2024-01-24", "Elon Musk", "TSLA", "Q4 실망 마진압박",     "negative", "EV/Auto", 5),
    ("2024-04-23", "Elon Musk", "TSLA", "저가모델 개발계획",    "positive", "EV/Auto", 5),
    ("2024-07-23", "Elon Musk", "TSLA", "로보택시 발표",        "positive", "EV/Auto", 5),
    ("2024-10-10", "Elon Musk", "TSLA", "로보택시 데이",        "positive", "EV/Auto", 6),
    ("2024-10-23", "Elon Musk", "TSLA", "Q3 실적서프라이즈",    "positive", "EV/Auto", 5),
    ("2025-01-29", "Elon Musk", "TSLA", "Q4 실적발표 부진",     "negative", "EV/Auto", 5),
    ("2025-04-22", "Elon Musk", "TSLA", "Q1 실적발표",          "negative", "EV/Auto", 5),
    ("2025-07-23", "Elon Musk", "TSLA", "Q2 실적부진(마진압박,관세우려)", "negative", "EV/Auto", 5),
    ("2025-10-22", "Elon Musk", "TSLA", "Q3 매출기록 그러나 이익감소", "negative", "EV/Auto", 5),

    # ═══ 🇺🇸 Jerome Powell (매크로) ═══
    ("2023-02-01", "Jerome Powell", "SPY",  "금리 0.25% 인상",   "negative", "Macro/Rates", 6),
    ("2023-05-03", "Jerome Powell", "QQQ",  "금리 5.25% 동결암시","positive","Macro/Rates", 6),
    ("2023-07-26", "Jerome Powell", "SPY",  "마지막 금리인상",    "positive", "Macro/Rates", 6),
    ("2023-11-01", "Jerome Powell", "SPY",  "금리동결 비둘기",    "positive", "Macro/Rates", 6),
    ("2024-01-31", "Jerome Powell", "SPY",  "금리동결 매파",      "negative", "Macro/Rates", 6),
    ("2024-03-20", "Jerome Powell", "QQQ",  "금리인하 시사",      "positive", "Macro/Rates", 6),
    ("2024-07-31", "Jerome Powell", "SPY",  "9월 인하 시사",      "positive", "Macro/Rates", 6),
    ("2024-09-18", "Jerome Powell", "SPY",  "빅컷 0.5% 인하",     "positive", "Macro/Rates", 6),
    ("2024-12-18", "Jerome Powell", "SPY",  "인하속도 조절",      "negative", "Macro/Rates", 6),
    ("2025-01-29", "Jerome Powell", "QQQ",  "금리동결 유지",      "neutral",  "Macro/Rates", 5),
    ("2025-03-19", "Jerome Powell", "SPY",  "스태그플레이션 경고","negative", "Macro/Rates", 6),
    ("2025-09-17", "Jerome Powell", "SPY",  "9월 0.25%p 인하(리스크관리 컷)", "neutral", "Macro/Rates", 6),
    ("2025-12-10", "Jerome Powell", "SPY",  "12월 0.25%p 인하 매파적 코멘트", "positive", "Macro/Rates", 6),

    # ═══ 🇺🇸 Sam Altman (OpenAI/AI관련주) ═══
    ("2023-03-14", "Sam Altman", "MSFT", "GPT-4 발표",          "positive", "Cloud/AI", 6),
    ("2023-11-17", "Sam Altman", "MSFT", "OpenAI 해임 후 복귀", "positive", "Cloud/AI", 5),
    ("2024-02-15", "Sam Altman", "MSFT", "Azure AI수요급증",    "positive", "Cloud/AI", 5),
    ("2024-05-13", "Sam Altman", "MSFT", "GPT-4o 발표",         "positive", "Cloud/AI", 5),
    ("2024-09-12", "Sam Altman", "NVDA", "칩수요 발언",         "positive", "AI/GPU", 4),
    ("2025-01-21", "Sam Altman", "MSFT", "Stargate 500B",       "positive", "Cloud/AI", 6),
    ("2025-02-10", "Sam Altman", "NVDA", "o3 모델 발표",        "positive", "AI/GPU", 5),
    ("2025-05-13", "Sam Altman", "MSFT", "GPT-4o 이미지 붐",   "positive", "Cloud/AI", 5),

    # ═══ 🇺🇸 Warren Buffett ═══
    ("2023-02-25", "Warren Buffett", "BRK-B", "연례서한 발표",   "positive", "Finance", 5),
    ("2023-11-14", "Warren Buffett", "AAPL",  "애플 추가매입",   "positive", "Tech/Finance", 5),
    ("2024-02-24", "Warren Buffett", "BRK-B", "연례서한 발표",   "positive", "Finance", 5),
    ("2024-05-04", "Warren Buffett", "AAPL",  "애플매도 발표",   "negative", "Tech/Finance", 6),
    ("2024-08-14", "Warren Buffett", "AAPL",  "애플 추가매도",   "negative", "Tech/Finance", 6),
    ("2024-11-14", "Warren Buffett", "BRK-B", "T-bill 현금보유", "neutral",  "Finance", 4),
    ("2025-02-22", "Warren Buffett", "BRK-B", "현금비축 역대최대","neutral", "Finance", 5),

    # ═══ 🇺🇸 Donald Trump (정책/관세) ═══
    ("2023-06-13", "Donald Trump", "SPY",  "연방법원 기소",      "negative", "Political", 4),
    ("2024-01-15", "Donald Trump", "SPY",  "아이오와 압승",      "positive", "Political", 5),
    ("2024-07-13", "Donald Trump", "SPY",  "암살시도 후 지지율↑","positive", "Political", 5),
    ("2024-11-06", "Donald Trump", "SPY",  "대선 승리",          "positive", "Political", 6),
    ("2025-01-20", "Donald Trump", "SPY",  "취임 + 행정명령",    "positive", "Political", 6),
    ("2025-02-01", "Donald Trump", "TSLA", "관세 발표 멕시코",   "negative", "Political", 6),
    ("2025-04-02", "Donald Trump", "SPY",  "상호관세 발표",      "negative", "Political", 6),
    ("2025-04-09", "Donald Trump", "SPY",  "관세 90일 유예",     "positive", "Political", 6),

    # ═══ 🇺🇸 Tim Cook (Apple) ═══
    ("2023-05-04", "Tim Cook", "AAPL", "FQ2 실적발표 견조",     "positive", "Tech", 5),
    ("2023-08-03", "Tim Cook", "AAPL", "FQ3 실적 iPhone 견조",  "positive", "Tech", 5),
    ("2023-11-02", "Tim Cook", "AAPL", "FQ4 실적발표",          "positive", "Tech", 5),
    ("2024-02-01", "Tim Cook", "AAPL", "FQ1 실적 중국 부진",    "negative", "Tech", 5),
    ("2024-05-02", "Tim Cook", "AAPL", "FQ2 250B 자사주매입",   "positive", "Tech", 6),
    ("2024-06-10", "Tim Cook", "AAPL", "WWDC AI 발표",          "positive", "Tech", 6),
    ("2024-08-01", "Tim Cook", "AAPL", "FQ3 서프라이즈",        "positive", "Tech", 5),
    ("2025-01-30", "Tim Cook", "AAPL", "FQ1 실적발표",          "positive", "Tech", 5),
    ("2025-05-01", "Tim Cook", "AAPL", "FQ2 실적발표",          "positive", "Tech", 5),
    ("2025-07-31", "Tim Cook", "AAPL", "FQ3 실적서프라이즈(아이폰 강세)", "positive", "Tech", 5),
    ("2025-10-30", "Tim Cook", "AAPL", "FQ4 실적서프라이즈+가이던스 상회", "positive", "Tech", 5),

    # ═══ 🇺🇸 Satya Nadella (Microsoft) ═══
    ("2023-04-25", "Satya Nadella", "MSFT", "FQ3 클라우드 호조", "positive", "Cloud/AI", 5),
    ("2023-07-25", "Satya Nadella", "MSFT", "FQ4 AI 매출급증",  "positive", "Cloud/AI", 5),
    ("2024-01-30", "Satya Nadella", "MSFT", "FQ2 코파일럿 성과", "positive", "Cloud/AI", 5),
    ("2024-04-25", "Satya Nadella", "MSFT", "FQ3 Azure AI 폭발","positive", "Cloud/AI", 6),
    ("2024-10-30", "Satya Nadella", "MSFT", "FQ1FY25 실적발표",  "positive", "Cloud/AI", 5),
    ("2025-01-29", "Satya Nadella", "MSFT", "FQ2FY25 클라우드↑", "positive", "Cloud/AI", 5),
    ("2025-10-29", "Satya Nadella", "MSFT", "FY26Q1 실적beat 그러나 Capex우려 급락", "negative", "Cloud/AI", 5),

    # ═══ 🇺🇸 Mark Zuckerberg (Meta) ═══
    ("2023-02-01", "Mark Zuckerberg", "META", "효율의 해 발표",  "positive", "Social/AI", 6),
    ("2023-04-26", "Mark Zuckerberg", "META", "Q1 광고회복",     "positive", "Social/AI", 5),
    ("2023-07-26", "Mark Zuckerberg", "META", "Q2 실적서프라이즈","positive","Social/AI", 6),
    ("2024-01-31", "Mark Zuckerberg", "META", "Q4 배당 첫 발표", "positive", "Social/AI", 6),
    ("2024-04-24", "Mark Zuckerberg", "META", "AI투자 과잉 우려","negative", "Social/AI", 5),
    ("2024-10-30", "Mark Zuckerberg", "META", "Q3 실적서프라이즈","positive","Social/AI", 6),
    ("2025-01-29", "Mark Zuckerberg", "META", "AI 에이전트 공개","positive", "Social/AI", 5),
]


# ──────────────────────────────────────────────────────────────
# 기술지표 계산 (12개)
# ──────────────────────────────────────────────────────────────

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0

def calc_macd_signal(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    if len(macd) < 2: return 0
    return 1 if (macd.iloc[-1] > sig.iloc[-1] and macd.iloc[-2] <= sig.iloc[-2]) \
             or macd.iloc[-1] > 0 else 0

def calc_volume_ratio(volume, window=20):
    avg = volume.rolling(window).mean().iloc[-1]
    return float(min(volume.iloc[-1] / (avg + 1), 5.0) / 5.0) if avg > 0 else 0.5

def calc_bollinger_pos(close, window=20):
    ma = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = ma + 2*std; lower = ma - 2*std
    pos = (close.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1] + 1e-9)
    return float(np.clip(pos, 0, 1))

def calc_momentum(close, days=5):
    if len(close) < days+1: return 0.5
    ret = (close.iloc[-1] - close.iloc[-(days+1)]) / (close.iloc[-(days+1)] + 1e-9)
    return float(np.clip(0.5 + ret * 5, 0, 1))

def calc_gap_up(df_pre, df_full, signal_pos):
    """갭상승 비율: 이벤트 당일 Open vs 전일 Close"""
    if signal_pos < 1: return 0.5
    prev_close = float(df_full['Close'].iloc[signal_pos - 1])
    event_open = float(df_full['Open'].iloc[signal_pos])
    gap = (event_open - prev_close) / (prev_close + 1e-9)
    return float(np.clip(0.5 + gap * 10, 0, 1))  # ±10% → 0~1

def calc_price_vs_52w(close):
    """현재가 / 52주 최고가 (낮을수록 저평가 상태)"""
    if len(close) < 10: return 0.5
    high_52w = close.rolling(min(len(close), 252)).max().iloc[-1]
    return float(np.clip(close.iloc[-1] / (high_52w + 1e-9), 0, 1))

def calc_atr_ratio(df, window=14):
    """ATR/Close — 변동성 상대 수준 (낮을수록 안정, 0~1)"""
    high = df['High']; low = df['Low']; close = df['Close']
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window).mean().iloc[-1]
    atr_ratio = atr / (close.iloc[-1] + 1e-9)
    return float(np.clip(1 - atr_ratio * 10, 0, 1))  # 높은 안정성 = 높은 점수

def calc_trend_dir(close, window=20):
    """20일 추세 방향: 선형회귀 기울기 양수=1, 음수=0"""
    if len(close) < window: return 0.5
    y = close.values[-window:]
    x = np.arange(window)
    slope = np.polyfit(x, y, 1)[0]
    return 1.0 if slope > 0 else 0.0

def calc_pre_run(close, days=5):
    """이벤트 전 5일 수익률 — 이미 많이 오른 경우 낮은 점수"""
    if len(close) < days+2: return 0.5
    ret = (close.iloc[-1] - close.iloc[-(days+1)]) / (close.iloc[-(days+1)] + 1e-9)
    # 이미 많이 오른 경우 낮은 기대수익 → 역수로 변환
    return float(np.clip(0.5 - ret * 3, 0, 1))

def calc_rsi_filter(rsi_val):
    """RSI 30~65구간이 진입 최적"""
    return 1.0 if 28 <= rsi_val <= 65 else 0.0

def calc_volume_surge(volume, window=20):
    """거래량 평균 대비 1.5배 이상이면 1"""
    avg = volume.rolling(window).mean().iloc[-1]
    ratio = volume.iloc[-1] / (avg + 1)
    return 1.0 if ratio >= 1.5 else 0.0


# ──────────────────────────────────────────────────────────────
# 이벤트 → 훈련 데이터 변환
# ──────────────────────────────────────────────────────────────

def fetch_event_data(date_str, symbol, hold_days=HOLD_DAYS):
    try:
        signal_date = datetime.strptime(date_str, "%Y-%m-%d")
        start = (signal_date - timedelta(days=120)).strftime("%Y-%m-%d")
        end   = (signal_date + timedelta(days=hold_days + 10)).strftime("%Y-%m-%d")

        df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
        if df.empty or len(df) < 25:
            return None

        df.index = pd.to_datetime(df.index).tz_localize(None)
        signal_dt = pd.Timestamp(signal_date)
        after = df[df.index >= signal_dt]
        if after.empty: return None

        signal_idx = after.index[0]
        signal_pos = df.index.get_loc(signal_idx)
        signal_price = float(df['Close'].iloc[signal_pos])

        pre = df.iloc[:signal_pos+1]
        if len(pre) < 25: return None

        result_pos = min(signal_pos + hold_days, len(df) - 1)
        result_price = float(df['Close'].iloc[result_pos])
        actual_return = (result_price - signal_price) / (signal_price + 1e-9)

        close  = pre['Close']
        volume = pre['Volume']
        rsi_val = calc_rsi(close)

        return {
            "signal_price": round(signal_price, 4),
            "result_price": round(result_price, 4),
            "actual_return": round(actual_return * 100, 2),
            "outcome": 1 if actual_return >= TARGET_RET else 0,
            "indicators": {
                # ── 기존 지표 ──
                "rsi_filter":   calc_rsi_filter(rsi_val),
                "rsi_raw":      round(rsi_val, 1),
                "macd_align":   float(calc_macd_signal(close)),
                "volume_surge": calc_volume_surge(volume),
                "volume_ratio": round(calc_volume_ratio(volume), 3),
                "bollinger_pos": round(calc_bollinger_pos(close), 3),
                "momentum_5d":  round(calc_momentum(close, 5), 3),
                # ── 신규 지표 ──
                "gap_up":       round(calc_gap_up(pre, df, signal_pos), 3),
                "price_vs_52w": round(calc_price_vs_52w(close), 3),
                "atr_stability": round(calc_atr_ratio(pre), 3),
                "trend_dir_20": calc_trend_dir(close, 20),
                "pre_run_inv":  round(calc_pre_run(close, 5), 3),
            }
        }
    except Exception as e:
        print(f"  ❌ {symbol} {date_str}: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 인물별 적중률
# ──────────────────────────────────────────────────────────────

def compute_person_hit_rates(results):
    from collections import defaultdict
    stats = defaultdict(lambda: {"total": 0, "hit": 0})
    for r in results:
        stats[r["person"]]["total"] += 1
        if r["outcome"] == 1:
            stats[r["person"]]["hit"] += 1
    return {p: s["hit"]/s["total"] if s["total"] else 0.5 for p, s in stats.items()}


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("📊 훈련 데이터 빌더 v2 — 실이벤트 200+ · 지표 12개")
    print("=" * 65)
    print(f"총 이벤트: {len(EVENTS)}건  |  보유기간: {HOLD_DAYS}일  |  목표수익: {TARGET_RET*100}%\n")

    raw_results = []
    for i, (date_str, person, symbol, statement, sentiment, sector, cv) in enumerate(EVENTS):
        print(f"[{i+1:03d}/{len(EVENTS)}] {person:18s} {symbol:12s} {date_str} — {statement}")
        data = fetch_event_data(date_str, symbol)
        if data is None:
            continue

        sent_map = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
        raw_results.append({
            "date": date_str, "person": person, "symbol": symbol,
            "statement": statement, "sector": sector, "sentiment": sentiment,
            "cross_val_raw": cv, "outcome": data["outcome"],
            "signal_price": data["signal_price"],
            "result_price": data["result_price"],
            "actual_return": data["actual_return"],
            "indicators_raw": data["indicators"],
            "_sent_val": sent_map.get(sentiment, 0.5),
            "_cross_norm": min(cv / 6.0, 1.0),
        })
        ret_str = f"{data['actual_return']:+.2f}%"
        out_str = "✅" if data["outcome"] == 1 else "❌"
        ind = data['indicators']
        print(f"       → {out_str} {ret_str}  RSI:{ind['rsi_raw']}  MACD:{ind['macd_align']}  Gap:{ind['gap_up']:.2f}  52w:{ind['price_vs_52w']:.2f}")

    if not raw_results:
        print("\n❌ 처리된 이벤트 없음")
        return

    hit_rates = compute_person_hit_rates(raw_results)

    final_signals = []
    for r in raw_results:
        hr = hit_rates.get(r["person"], 0.5)
        ind = r["indicators_raw"].copy()
        ind["hit_rate"]        = round(hr, 3)
        ind["sentiment"]       = r["_sent_val"]
        ind["cross_val"]       = r["_cross_norm"]
        ind["news_freq"]       = round(min(r["cross_val_raw"] / 6.0, 1.0), 3)
        ind["signal_strength"] = round((r["_sent_val"] + ind["macd_align"] + ind["rsi_filter"]) / 3.0, 3)
        final_signals.append({
            "id": len(final_signals),
            "date": r["date"], "person": r["person"],
            "symbol": r["symbol"], "sector": r["sector"],
            "sentiment": r["sentiment"], "statement": r["statement"],
            "outcome": r["outcome"],
            "signal_price": r["signal_price"],
            "result_price": r["result_price"],
            "actual_return": r["actual_return"],
            "indicators": ind,
        })

    total = len(final_signals)
    wins  = sum(s["outcome"] for s in final_signals)
    print(f"\n{'='*65}")
    print(f"✅ 처리 완료: {total}건  |  수익달성: {wins}건 ({wins/total*100:.1f}%)")
    print(f"\n  {'인물':<22} {'신호':>5} {'적중':>5} {'적중률':>8}")
    print(f"  {'─'*44}")
    for person, hr in sorted(hit_rates.items(), key=lambda x:-x[1]):
        sigs = [s for s in final_signals if s["person"] == person]
        hits = sum(s["outcome"] for s in sigs)
        print(f"  {person:<22} {len(sigs):>5} {hits:>5} {hr*100:>7.1f}%")

    os.makedirs("data", exist_ok=True)
    output = {
        "generated_at": datetime.now().isoformat(),
        "version": "v2",
        "total_signals": total,
        "positive_rate": round(wins/total, 3),
        "hold_days": HOLD_DAYS,
        "target_return": TARGET_RET,
        "hit_rates_by_person": {k: round(v,3) for k,v in hit_rates.items()},
        "signals": final_signals,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n💾 저장: {OUTPUT_PATH} ({total}건)")
    print("=" * 65)

if __name__ == "__main__":
    main()
