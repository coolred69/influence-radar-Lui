// Firebase Messaging Service Worker
// influence-radar 전용 백그라운드 푸시 알림

importScripts('https://www.gstatic.com/firebasejs/11.5.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/11.5.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyAl9w26mpnGSTHe-lHBtRFWkIv3tRbA0p8",
  authDomain: "influence-radar-43a48.firebaseapp.com",
  projectId: "influence-radar-43a48",
  storageBucket: "influence-radar-43a48.firebasestorage.app",
  messagingSenderId: "1008784285984",
  appId: "1:1008784285984:web:788217edf21b10eb6e3745",
});

const messaging = firebase.messaging();

// 백그라운드 메시지 수신 (앱 꺼져있을 때)
messaging.onBackgroundMessage((payload) => {
  console.log('[SW] 백그라운드 메시지 수신:', payload);

  const { title, body, icon } = payload.notification || {};
  const score = payload.data?.score || 0;

  const emoji = score >= 70 ? '🔴' : score >= 45 ? '🟠' : score >= 25 ? '🟡' : '📡';
  const label = score >= 70 ? '즉시포착' : score >= 45 ? '유망 시그널' : score >= 25 ? '관찰' : '뉴스';

  self.registration.showNotification(`${emoji} ${label} — ${title || 'Influence Radar'}`, {
    body: body || '새 시그널이 감지됐습니다',
    icon: icon || '/influence-radar.html',
    badge: '/influence-radar.html',
    tag: `signal-${score}`,
    requireInteraction: score >= 70, // 즉시포착은 직접 닫아야
    vibrate: score >= 70 ? [200,100,200,100,200] : score >= 45 ? [200,100,200] : [100],
    data: { url: '/influence-radar.html', score },
    actions: score >= 45 ? [
      { action: 'open', title: '📊 레이더 열기' },
      { action: 'dismiss', title: '닫기' },
    ] : [],
  });
});

// 알림 클릭 시 레이더 열기
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if(event.action === 'dismiss') return;

  event.waitUntil(
    clients.matchAll({type:'window', includeUncontrolled:true}).then(clientList => {
      for(const client of clientList) {
        if(client.url.includes('influence-radar') && 'focus' in client) {
          return client.focus();
        }
      }
      if(clients.openWindow) {
        return clients.openWindow('./influence-radar.html');
      }
    })
  );
});
