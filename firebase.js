// firebase.js — Firebase 초기화 및 Firestore/FCM 연동
// influence-radar 모듈화 1단계
// 수정 시 이 파일만 건드릴 것

import { initializeApp } from 'https://www.gstatic.com/firebasejs/11.5.0/firebase-app.js';
import { getFirestore, doc, setDoc, getDoc, onSnapshot, serverTimestamp }
  from 'https://www.gstatic.com/firebasejs/11.5.0/firebase-firestore.js';
import { getMessaging, getToken, onMessage }
  from 'https://www.gstatic.com/firebasejs/11.5.0/firebase-messaging.js';

const firebaseConfig = {
  apiKey: "AIzaSyAI9w26mpnG5The-1HBtRFWkIv3rRbA0p8",
  authDomain: "influence-radar-43a48.firebaseapp.com",
  projectId: "influence-radar-43a48",
  storageBucket: "influence-radar-43a48.firebasestorage.app",
  messagingSenderId: "1008784285984",
  appId: "1:1008784285984:web:788217edf21b10eb6e3745",
  measurementId: "G-61HY2F2WD8"
};

const fbApp = initializeApp(firebaseConfig);
const db = getFirestore(fbApp);

// ── Firestore 저장
window.fbSave = async function(data) {
  try {
    await setDoc(doc(db,'radar','main'), {
      logs: data.logs || [],
      alerts: (data.alerts||[]).slice(0,100),
      learnData: data.learnData || {},
      signalLog: (data.signalLog||[]).slice(0,500),
      trades: (data.trades||[]).slice(0,200),
      updatedAt: serverTimestamp(),
    }, {merge:true});
  } catch(e) { console.warn('FB save error:', e); }
};

// ── Firestore 불러오기
window.fbLoad = async function() {
  try {
    const snap = await getDoc(doc(db,'radar','main'));
    if(snap.exists()) return snap.data();
  } catch(e) { console.warn('FB load error:', e); }
  return null;
};

// ── 실시간 동기화
window.fbListen = function(callback) {
  return onSnapshot(doc(db,'radar','main'), (snap) => {
    if(snap.exists()) callback(snap.data());
  });
};

// ── FCM 푸시 알림
const VAPID_KEY = 'BAR--UDhhWLNMM11VJVrkIkMvLHzH5nFgQoqfEkaOPtXjQrwmZkisECFzIKpZ3yZhX9sbaiV3HhbTM_i5MwGTfw';

window.fbInitFCM = async function() {
  try {
    const messaging = getMessaging(fbApp);
    const token = await getToken(messaging, {vapidKey: VAPID_KEY});
    localStorage.setItem('ir_fcm_token', token);
    console.log('✅ FCM Token 발급 완료');

    onMessage(messaging, (payload) => {
      const {title, body} = payload.notification || {};
      if(title && window.pushNotif) window.pushNotif(title, body||'', 70, '');
    });

    const fbSt = document.getElementById('fb-status');
    if(fbSt) { fbSt.textContent = '🔥 FB+FCM 완료'; fbSt.style.color = '#16a34a'; }
    return token;
  } catch(e) {
    console.warn('FCM init error:', e);
    return null;
  }
};

// 전역 노출
window.db = db;
window.fbReady = true;
console.log('✅ Firebase 연결 완료 (firebase.js)');
