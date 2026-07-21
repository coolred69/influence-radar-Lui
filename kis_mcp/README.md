# KIS 한국투자증권 통합 MCP 서버

한국 + 미국 주식 실시간 시세 / 모의매매 / 학습 루프

---

## 1. 설치

```bash
cd C:\Githubdesktop\influence-radar-lui\kis_mcp
install.bat
```

또는 수동:
```bash
pip install mcp httpx python-dotenv
```

---

## 2. .env 설정

`.env` 파일에 계좌번호 앞 8자리 입력:

```
KIS_APP_KEY=발급받은_APP_KEY_입력
KIS_APP_SECRET=발급받은_APP_SECRET_입력
KIS_ACCOUNT_NO=12345678   ← 여기 입력
```

계좌번호 확인: 한투 앱 → 계좌 → 앞 8자리

---

## 3. Claude Desktop 등록

`C:\Users\whiph\AppData\Roaming\Claude\claude_desktop_config.json` 열어서 mcpServers 에 추가:

```json
{
  "mcpServers": {
    "kis-trading": {
      "command": "python",
      "args": ["C:\\Githubdesktop\\influence-radar-lui\\kis_mcp\\kis_mcp_server.py"]
    }
  }
}
```

기존 mcpServers 항목이 있으면 그 안에 `"kis-trading": { ... }` 만 추가.

---

## 4. Claude 재시작

설정 저장 후 Claude Desktop 완전 종료 → 재시작

---

## 5. 사용 가능한 툴

### 한국 주식
| 툴 | 설명 |
|---|---|
| `get_kr_stock_price` | 실시간 현재가 |
| `get_kr_stock_history` | 일/주/월봉 |
| `place_kr_order` | 매수/매도 주문 |
| `get_kr_account_balance` | 잔고 조회 |

### 미국 주식
| 툴 | 설명 |
|---|---|
| `get_us_stock_price` | 실시간 현재가 |
| `get_us_stock_history` | 일/주/월봉 |
| `place_us_order` | 매수/매도 주문 |
| `get_us_account_balance` | 잔고 조회 |

### 학습 루프
| 툴 | 설명 |
|---|---|
| `log_trade_entry` | 매매 추천 기록 (진입 시) |
| `log_trade_exit` | 결과 기록 (청산 시) |
| `get_performance_report` | 성과 분석 리포트 |
| `get_open_positions` | 오픈 포지션 확인 |
| `get_trade_history` | 전체 매매 이력 |

### 공통
| 툴 | 설명 |
|---|---|
| `search_stock` | 종목명/티커 검색 |

---

## 6. 학습 루프 흐름

```
1. Claude 가 종목 분석
2. log_trade_entry() → 추천 근거 + 확신도 기록
3. place_kr/us_order() → 모의 주문 실행
4. (며칠 후) log_trade_exit() → 결과 기록
5. get_performance_report() → 승률/수익률/확신도별 분석
6. 패턴 발견 → 다음 추천에 반영
```

---

## 7. 보안 주의

- `.env` 파일을 GitHub 에 올리지 마세요 (`.gitignore` 에 추가)
- App Secret 은 채팅에 공유하지 마세요
- 테스트 후 apiportal.koreainvestment.com 에서 키 재발급 권장

---

## 8. 지원 거래소

| 코드 | 거래소 |
|---|---|
| NASD | NASDAQ |
| NYSE | 뉴욕증권거래소 |
| AMEX | AMEX |
