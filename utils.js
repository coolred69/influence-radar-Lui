// utils.js — 공유 순수 헬퍼 함수
// influence-radar + korea-radar 공통 사용
// 외부 의존성 없음 (state, Firebase 참조 안 함)

// ── 종목 코드 파싱
function splitTk(val) {
  if (!val) return [];
  if (Array.isArray(val)) return val.filter(Boolean);
  return String(val).split(/[·,]+/).map(t => t.trim()).filter(Boolean);
}

// ── 기회점수 계산
const opp = (inf, f, d) => Math.round((inf / 100) * (f / 100) * Math.abs(d) * 10);
const oppLabel = s => s >= 70 ? '🔴 즉시포착' : s >= 45 ? '🟠 유망' : s >= 25 ? '🟡 관찰' : '⚫ 필터아웃';
const oppClass = s => s >= 70 ? 'opp-red' : s >= 45 ? 'opp-orange' : s >= 25 ? 'opp-yellow' : 'opp-grey';
const oppBorder = s => s >= 70 ? '#ff4444' : s >= 45 ? '#ff8c00' : s >= 25 ? '#fbbf24' : '#2a2a4a';

// ── 금액 포맷
function fmtUSD(n) {
  if (n >= 1000000) return '$' + (n / 1000000).toFixed(2) + 'M';
  if (n >= 1000) return '$' + (n / 1000).toFixed(1) + 'K';
  return '$' + n.toFixed(2);
}

function fmtKRW(n) {
  if (n >= 100000000) return (n / 100000000).toFixed(1) + '억';
  if (n >= 10000) return (n / 10000).toFixed(0) + '만';
  return n.toLocaleString('ko-KR');
}

// ── HTML 컴포넌트 헬퍼
function tag(text, color, sm) {
  return `<span class="tag" style="color:${color};border-color:${color}44;background:${color}15;font-size:${sm ? '8px' : '10px'}">${text}</span>`;
}

function bar(v, color, w = 60) {
  const pct = Math.min(v, 100);
  const c = color || (v >= 70 ? '#16a34a' : v >= 50 ? '#fbbf24' : '#ef4444');
  return `<div style="width:${w}px;height:4px;background:#1a1a3a;border-radius:2px;overflow:hidden">
    <div style="width:${pct}%;height:100%;background:${c};border-radius:2px;transition:width 0.3s"></div>
  </div>`;
}

// ── 점수 색상
function scoreColor(s) {
  if (s >= 70) return '#ff4444';
  if (s >= 50) return '#ff8c00';
  if (s >= 30) return '#fbbf24';
  return '#556677';
}

// ── 등락률 색상
function changeColor(pct) {
  if (pct > 0) return '#16a34a';
  if (pct < 0) return '#dc2626';
  return '#556677';
}

function changeArrow(pct) {
  return pct > 0 ? '▲' : pct < 0 ? '▼' : '';
}

// ── 발언 순수 효과 계산
function pureEffect(log) {
  if (log.drop <= 0) return null;
  const pe = log.drop - (log.spDrop || 0) - ((log.sectorDrop || 0) * 0.3);
  return Math.round(pe * 10) / 10;
}

function peLabel(pe) {
  if (pe === null) return null;
  if (pe >= 8) return { text: '발언 단독효과 높음', color: '#ff4444' };
  if (pe >= 4) return { text: '발언+시장 혼합', color: '#ff8c00' };
  if (pe >= 1) return { text: '발언 효과 미미', color: '#fbbf24' };
  return { text: '시장 흐름 탓 (발언 무관)', color: '#2563eb' };
}

// ── 온도 정보
function tempInfo(t) {
  if (t >= 75) return { text: `과열 ${t}`, cls: 'temp-hot' };
  if (t >= 55) return { text: `정상 ${t}`, cls: 'temp-warm' };
  if (t >= 35) return { text: `냉각 ${t}`, cls: 'temp-cool' };
  return { text: `저온 ${t}`, cls: 'temp-cold' };
}

// ── 날짜 포맷
function fmtDate(d) {
  const dt = d instanceof Date ? d : new Date(d);
  return dt.toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

// ── 숫자 클램프
function clamp(v, min, max) {
  return Math.min(Math.max(v, min), max);
}

console.log('✅ utils.js 로드 완료');
