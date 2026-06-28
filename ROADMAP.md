# Influence Radar — 개발 로드맵

> 루이 관리 문서 | 매 세션 시작 시 참조할 것
> 마지막 업데이트: 2026-06-28

---

## 프로젝트 개요

**목적:** 글로벌 영향력자(Trump·Musk 등) 발언을 실시간 감지 → 주식 시그널 자동 생성 → 누적 학습으로 정확도 향상

**스택:** 단일 HTML(GitHub Pages) + Flask 백엔드(Render.com 무료) + Firebase(데이터 동기화)

**핵심 파일:**
- `influence-radar.html` — 메인 앱 (~5700줄)
- `data.js` — 인물·섹터·패턴 데이터 (분리 완료)
- `app.py` — Render 백엔드 (ML API)

---

## 완료된 작업

### 모듈화 (2026-06-28)
- [x] **firebase.js** 분리 — Firebase 초기화·Firestore·FCM
- [x] **utils.js** 공유 모듈 — 순수 헬퍼 함수 (opp, fmtKRW, tag, bar 등)
- [x] **index.html** 메인 허브 개편 — 미국/한국 탭 분기
- [x] **korea-radar.html** 한국 퀀트 스크리너 구축
  - Yahoo Finance v8/chart API (v7 401 차단 → v8 우회)
  - 28종목 스캔, 5개 병렬 배치 조회
  - 거래량 급증 · 52주 돌파 직전 · 저PBR 점수화

### 기반 구조
- [x] Firebase Firestore 연동 (데이터 영구 보존)
- [x] FCM 푸시 알림
- [x] PWA 설정 (홈화면 추가)
- [x] Render.com 배포 + keepalive (8분마다)
- [x] `data.js` 분리 — FIGS·SM·PATTERNS·INIT_LOGS 모듈화 (2026-06-07)
- [x] HTML 내부 섹션 마커 추가 (STATE / HELPERS / LOGIC / UI)

### 인물·섹터
- [x] 9명 고정: Trump·Musk·Powell·Xi·Jensen·Buffett·Dimon·Altman·MBS
- [x] 12개 섹터: AI·반도체·EV·크립토·에너지·금융·중국테크·로봇·방위·의료·소비·부동산
- [x] 인물별 twitter·googleAlert 필드 추가

### 뉴스 수집
- [x] Currents API (실시간, 상위 2명)
- [x] GNews API (12시간 지연, 나머지 인물)
- [x] **Nitter RSS** — Trump·Musk·Jensen·Altman 자동 감시, 15분 폴링, 4개 인스턴스 fallback (2026-06-07)
- [x] **Google Alerts RSS** — 9명 전원, 설정 UI (종목발굴 탭 하단) (2026-06-07)

### 시그널·학습
- [x] 감성분석 (키워드 기반 규칙)
- [x] 기회점수 계산 (영향력 × 섹터강도 × 하락폭)
- [x] 가상 투자 시뮬레이션 (딥바이 + 트레일링 스탑)
- [x] 자동 결과 추적 (예측 기일 도달 시 Yahoo Finance 실가 수집)
- [x] 인물별 트레일링% 자동 학습
- [x] 학습 대시보드

---

## 진행 중 / 단기 과제

### 품질 개선 (우선순위 높음)
- [ ] **감성분석 고도화** — 키워드 카운팅 → 맥락 기반 (예: "tariff relief" vs "tariff hike" 구분)
- [ ] **Google Alerts 키워드 최적화** — 노이즈 줄이고 발언·결정 중심으로 정제
- [ ] Nitter 인스턴스 생존율 모니터링 + 자동 교체 로직

### 백테스트 (2026-06-28 완료)
- [x] **T+3 백테스트 28이벤트 실행** — Node.js + Yahoo Finance API (`outputs/backtest_t3.mjs`)
  - 전체 적중률 40.6% / Trump EV+6.85% / Musk EV+9.01%
  - COIN 100%, TSLA 83%, AMD 0%, BABA 25%
- [x] **data.js 가중치 업데이트** (commit ec215c3)
  - COIN f:65→92, TSLA f:61→88, MSTR f:58→85
  - AMD f:78→50, BABA f:67→48 (신뢰도 하향)
  - Jensen inf:84→72 (발표 선반영, 기댓값 -2.82%)
- [x] **INIT_LOGS 10건** 실측 검증 데이터로 보강
- [x] **과잉반응 딥바이 판별** — fetchFundamentals → evalOverreaction → renderOverreactionSection (💎 카드)

**백테스트 핵심 인사이트:**
- 유효 신호: Trump·Musk (기댓값 양수, 집중 종목 COIN·TSLA)
- 무효 신호: Jensen (선반영), AMD·BABA (방향 역전 빈번)
- 현재 28건 → 통계 유의성 위해 50건+ 필요

### 데이터 축적
- [ ] 실제 시그널 50건 이상 누적 (현재 28건 백테스트 + 10건 INIT_LOGS)
- [ ] 실 신호 지속 축적 → 가중치 자동 업데이트

---

## 중기 과제

### 아키텍처
- [ ] `logic.js` 분리 — ML 호출·트레일링·학습 로직
- [ ] `ui.js` 분리 — 렌더링·이벤트 핸들러
- [ ] 기능 추가 시 패치 스크립트 → 모듈 직접 수정 방식으로 전환

### 기능 확장
- [ ] **"원인불명 급락" 스크리너** (미국) — SPY/섹터ETF 대비 괴리율 계산, 발언 충격 의심 종목
- [ ] **korea-radar PBR 보강** — v10/quoteSummary 추가 조회 (현재 PBR 미지원)
- [ ] 감성분석 ML 모델 연동 (Render 백엔드 활용)
- [ ] 인물별 발언 캘린더 (FOMC 일정 등 고정 일정 자동 등록)
- [ ] 시그널 히스토리 차트 (인물별 적중률 시각화)
- [ ] 알림 커스터마이징 (인물별 ON/OFF, 점수 임계값 설정)

---

## 장기 과제 (수익화 관련)

- [ ] 뉴스 속도 개선 — X API Basic($100/월) 검토 (현재 Nitter RSS로 대체 중)
- [ ] 실제 매매 연동 검토 (현재는 시뮬레이션만)
- [ ] 멀티유저 지원 (현재 단일 유저)

---

## 알려진 문제

| 문제 | 원인 | 상태 |
|---|---|---|
| GNews 12시간 지연 | 무료 플랜 한계 | Nitter RSS로 보완 중 |
| Nitter 인스턴스 불안정 | 비공식 서비스 | fallback 4개로 대응 |
| Render 15분 슬립 | 무료 티어 | keepalive로 대응 |
| 감성분석 노이즈 | 키워드 카운팅 방식 | 개선 예정 |
| 학습 데이터 부족 | 실제 누적 필요 | 시간 해결 |

---

## 개발 규칙

1. **데이터 수정** → `data.js`만 건드릴 것
2. **기능 추가** → 섹션 마커 확인 후 해당 위치에 삽입
3. **수정 전** → git commit으로 스냅샷 저장
4. **파일 접근** → `mcp__Windows-MCP__PowerShell` 또는 Python 패치 스크립트 사용
5. **배포** → 항상 `git add -A && git commit && git push`까지
