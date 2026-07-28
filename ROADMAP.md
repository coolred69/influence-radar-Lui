# Influence Radar — 개발 로드맵

> 루이 관리 문서 | 매 세션 시작 시 참조할 것
> 마지막 업데이트: 2026-07-28 (커밋 이력 기준 재검증 후 갱신)

---

## ⚠️ 긴급 — GitHub 동기화 끊김 (2026-07-28 발견)

**증상:** GitHub `origin/main`이 **2026-07-14 09:13 KST 커밋(`f189e2c`, Signal Engine 봇 업데이트)에서 멈춰 있음.** 로컬 저장소는 그 이후로도 계속 커밋되어 **2026-07-23 12:39 KST(`0410341`)까지 진행됨** — 즉 로컬에만 존재하고 GitHub엔 반영 안 된 커밋이 **약 17개, 9일치.**

| 구분 | 상태 |
|---|---|
| 로컬 최신 커밋 | `0410341` — 2026-07-23 12:39 KST |
| GitHub(origin/main) 최신 커밋 | `f189e2c` — 2026-07-14 09:13 KST |
| 미반영 커밋 수 | 약 17개 (ML 파이프라인 v2, 보안 패치 3건, 지표 튜닝 등 포함) |
| 영향 범위 | GitHub Pages 배포본, GitHub Actions 자동 워크플로우가 보는 코드 — 모두 07-14 시점 코드로 정지 |

**원인 추정 (미확정 — 검증 필요):** `git push`가 실패했는데 이후 `git pull --rebase origin main`이 매번 "성공"으로 표시되면서 동기화된 것처럼 보였을 가능성이 높음. 코드/로직 문제 아님 — **push 누락 문제.**

**Action Plan (최우선)**
1. GitHub Desktop 또는 터미널에서 `origin/main` 대비 로컬 `ahead` 커밋 수 확인
2. push 재시도 — 실패 시 에러 메시지 확인 (인증 만료/브랜치 보호 규칙/충돌 여부)
3. push 성공 후 GitHub Actions(Signal Engine, Indicator Lab, Regime Detector, KIS 가격수집)가 07-14 이후 코드로 재개되는지 확인
4. **본 세션에서는 로컬 shell 접근이 막혀 있어 Claude가 직접 push 실행 불가 — 사용자 측에서 push 필요**

---

## 프로젝트 개요

**목적:** 글로벌 영향력자(Trump·Musk 등) 발언을 실시간 감지 → 주식 시그널 자동 생성 → 누적 학습으로 정확도 향상

**스택:** 단일 HTML(GitHub Pages) + Flask 백엔드(Render.com 무료) + Firebase(데이터 동기화) + Python ML 파이프라인(GitHub Actions)

**핵심 파일:**
- `influence-radar.html` — 메인 앱 (미국)
- `korea-radar.html` — 한국 퀀트 스크리너
- `signal-dashboard.html` — 매수 신호 대시보드
- `data.js` / `firebase.js` / `utils.js` — 공유 모듈
- `indicator_lab.py` / `signal_engine.py` / `optimize_params.py` / `track_signals.py` — ML/시그널 파이프라인
- `app.py` — Render 백엔드 (ML API)

---

## 완료된 작업

### 데이터 파이프라인·보안 (2026-07-01 ~ 07-23, 로컬 기준)
- [x] **한국주식 KIS 연동** — data.js KR 인플루언서 4인 추가, GitHub Actions KR 가격 수집
- [x] **Indicator Lab v2** — 실데이터 200건+, 지표 12개, scipy 최적화, Train/Test split, 5세대 자동 진화(GitHub Actions), 지표풀 17→23 확장 + stepwise 탐색
- [x] **Signal Engine** — 매수가/목표가/손절가/손익비(ATR 기반) 자동 계산, signal-dashboard.html
- [x] **Phase 2+3** — 파라미터 최적화(optimize_params.py) + 실전 피드백 루프(track_signals.py)
- [x] **Phase 4** — AI 트레이딩 실패 교훈 누적 시스템
- [x] **ML 파이프라인 v2** — training_data.json 127→142건 실전 데이터 연동, backtest/predict 스키마 통일
- [x] **보안 패치 3건** — Firebase API 키 노출 교체, KIS API SSL 검증 활성화(verify=True), README 노출 키 예시 제거
- [x] **Firestore 보안 규칙** — read-only public 적용
- [x] **weekly-retrain 워크플로우 버그 수정** — dirty tree exit 128 해결

### 모듈화 (2026-06-28)
- [x] **firebase.js** 분리 — Firebase 초기화·Firestore·FCM
- [x] **utils.js** 공유 모듈
- [x] **index.html** 메인 허브 개편 — 미국/한국 탭 분기
- [x] **korea-radar.html** 한국 퀀트 스크리너 — Yahoo Finance v8/chart API, 28종목 스캔

### 기반 구조
- [x] Firebase Firestore 연동, FCM 푸시, PWA 설정
- [x] Render.com 배포 + keepalive (8분마다)
- [x] `data.js` 분리 — FIGS·SM·PATTERNS·INIT_LOGS 모듈화

### 인물·섹터
- [x] 9명 고정(미국) + 4명(한국): Trump·Musk·Powell·Xi·Jensen·Buffett·Dimon·Altman·MBS
- [x] 12개 섹터 매핑

### 뉴스 수집
- [x] Currents API / GNews API / Nitter RSS(15분 폴링) / Google Alerts RSS(9명 전원)

### 시그널·학습
- [x] 감성분석(키워드 기반), 기회점수 계산, 가상 투자 시뮬레이션(딥바이+트레일링 스탑)
- [x] 자동 결과 추적, 인물별 트레일링% 자동 학습, 학습 대시보드
- [x] 과잉반응 딥바이 판별 (Yahoo Finance 펀더멘털 체크)

### 백테스트 (2026-06-28 기준, 갱신 필요)
- [x] T+3 백테스트 28이벤트 — 전체 적중률 40.6% / Trump EV+6.85% / Musk EV+9.01%
- [x] data.js 가중치 업데이트 (COIN/TSLA/MSTR 상향, AMD/BABA 하향)
- [x] INIT_LOGS 10건 → 이후 15건 추가 (142건 규모로 확대)

---

## 진행 중 / 단기 과제

### 최우선
- [ ] **GitHub push 동기화 복구** (위 긴급 섹션 참조)
- [ ] push 실패 재발 방지 — commit 후 push 성공 여부 명시적 확인 습관화

### 품질 개선
- [ ] **감성분석 고도화** — 키워드 카운팅 → 맥락 기반 구분
- [ ] **Google Alerts 키워드 최적화** — 노이즈 감소
- [ ] Nitter 인스턴스 생존율 모니터링 + 자동 교체 로직
- [ ] 백테스트 갱신 — 07-14 이후 축적된 데이터(142건+) 기준 재실행 필요 (06-28 결과는 28건 기준으로 낡음)

### 데이터 축적
- [ ] 실 신호 지속 축적 → 가중치 자동 업데이트 (push 복구 후 재개)

---

## 중기 과제

### 아키텍처
- [ ] `logic.js` 분리 — ML 호출·트레일링·학습 로직
- [ ] `ui.js` 분리 — 렌더링·이벤트 핸들러

### 기능 확장
- [ ] "원인불명 급락" 스크리너 (미국)
- [ ] korea-radar PBR 보강 (v10/quoteSummary)
- [ ] 감성분석 ML 모델 연동
- [ ] 인물별 발언 캘린더 (FOMC 등)
- [ ] 시그널 히스토리 차트, 알림 커스터마이징

---

## 장기 과제 (수익화 관련)

- [ ] 뉴스 속도 개선 — X API Basic($100/월) 검토
- [ ] 실제 매매 연동 검토
- [ ] 멀티유저 지원

---

## 알려진 문제

| 문제 | 원인 | 상태 |
|---|---|---|
| **GitHub push 미반영 (9일, 17커밋)** | push 실패 후 감지 안 됨 | 🔴 최우선 조치 필요 |
| GNews 12시간 지연 | 무료 플랜 한계 | Nitter RSS로 보완 중 |
| Nitter 인스턴스 불안정 | 비공식 서비스 | fallback 4개로 대응 |
| Render 15분 슬립 | 무료 티어 | keepalive로 대응 |
| 감성분석 노이즈 | 키워드 카운팅 방식 | 개선 예정 |
| 백테스트 결과 낡음 | 06-28 이후 데이터 미반영 | 재실행 필요 |

---

## 개발 규칙

1. **데이터 수정** → `data.js`만 건드릴 것
2. **기능 추가** → 섹션 마커 확인 후 해당 위치에 삽입
3. **수정 전** → git commit으로 스냅샷 저장
4. **배포** → 항상 `git add -A && git commit && git push`까지 — **push 후 origin 반영 여부 확인 필수 (이번 사고 재발 방지)**
