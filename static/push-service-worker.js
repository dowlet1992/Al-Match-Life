'use strict';

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

function safeEmail(value) {
    const email = String(value || '').trim().toLowerCase();
    return /^[^\s/@]+@[^\s/@]+\.[^\s/@]+$/.test(email) ? email : '';
}

self.addEventListener('push', event => {
    event.waitUntil((async () => {
        let data = {};
        try { data = event.data ? event.data.json() : {}; } catch (_) { return; }
        if (!data || !['incoming_call', 'call_cancelled'].includes(data.event_type)) return;
        const expiresAt = Number(data.expires_at || 0);
        if (!Number.isFinite(expiresAt) || expiresAt <= Date.now() / 1000) return;
        const callTag = `incoming-call-${String(data.call_id || '')}`;
        if (data.event_type === 'call_cancelled') {
            const notifications = await self.registration.getNotifications({ tag: callTag });
            notifications.forEach(notification => notification.close());
            return;
        }
        const caller = safeEmail(data.caller_email);
        const receiver = safeEmail(data.receiver_email);
        if (!caller || !receiver) return;
        const target = `/chat/${encodeURIComponent(receiver)}/${encodeURIComponent(caller)}`;
        await self.registration.showNotification('AI Match Life', {
            body: data.call_type === 'video' ? 'Incoming video call' : 'Incoming audio call',
            tag: callTag,
            renotify: true,
            requireInteraction: false,
            data: { target },
            actions: [{ action: 'open', title: 'Open call' }],
        });
    })());
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    const target = event.notification.data && event.notification.data.target;
    if (!target) return;
    event.waitUntil((async () => {
        const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const client of windows) {
            if ('focus' in client) {
                await client.navigate(target);
                return client.focus();
            }
        }
        return self.clients.openWindow(target);
    })());
});
