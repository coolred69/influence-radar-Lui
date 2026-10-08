path = '_health_logs/daily_health_log.md'
with open(path, encoding='utf-8') as f:
    content = f.read()

new_row = (
    "| 2026-10-08 | 93 | 0.7137 | 54.02 | 48.88 | 28.25 | 178 | 83(불일치 4일차, 지표상 정상판단) | "
    "정상 작동 중(Signal Engine/US+KR 종합확률/Health Check 10/7 19:39-20:03 UTC 성공 확인, gen 동일=평일 정상). "
    "Track C 10/7 06:28 UTC 성공, universe 정상/excluded 9·flagged 42·clean 785(전일 급증 없음). "
    "펀더멘털 US 10/4 커밋 확인(8일 이내), KR은 git log상 9/27 마지막 커밋이나 워크플로우 로그 확인 결과 "
    "10/4 런도 정상 실행되어 10종목 파일 생성 후 git diff 없음(DART 데이터 무변동)으로 커밋 생략된 것 확인"
    "—정지 아님, 정상. combined_probability_table 10/7 19:39 UTC 갱신(24h 이내). 상위3: GOOGL 62.5/AMZN 58.4/AAPL 57.8. "
    "total_signals=178이 9/29부터 10일째 정체(데이터 신규 축적 없음, 관찰 필요). "
    "backtest_report.json은 리포 루트 위치 확인(총178건, accuracy 34.27%, avg_return 1.47% — optimal_metrics와 별개 지표). "
    "Gmail 실패메일 0건=gh 전부 success 일치. 로컬 미커밋 변경 없음(pull만 수행, ddfcd8c->014c7ca). |"
)

content = content.rstrip('\n') + '\n' + new_row + '\n'
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('APPENDED')
