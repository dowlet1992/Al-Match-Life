(function(){
    const languageSelect = document.getElementById('interfaceLanguage');
    const csrfInput = document.querySelector('input[name="csrf_token"]');
    if (!languageSelect) return;
    let savedLanguage = languageSelect.value;

    languageSelect.addEventListener('change', async function(){
        const selectedLanguage = languageSelect.value;
        const template = languageSelect.dataset.languageUrlTemplate || '';
        if (!template || !csrfInput) return;
        languageSelect.disabled = true;
        try {
            const response = await fetch(template.replace('__language__', encodeURIComponent(selectedLanguage)), {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'X-CSRF-Token': csrfInput.value,
                    'X-Requested-With': 'fetch',
                    'Accept': 'application/json',
                },
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || !payload.ok) throw new Error('language_update_failed');
            savedLanguage = payload.language;
            window.location.assign(payload.redirect || window.location.href);
        } catch (error) {
            languageSelect.value = savedLanguage;
            languageSelect.disabled = false;
            window.alert(languageSelect.dataset.languageError);
        }
    });
})();

(function(){
    const input = document.getElementById('settingsSearch');
    const empty = document.getElementById('settingsEmpty');
    const sections = Array.from(document.querySelectorAll('form > .card[id]'));

    if (!input || !empty || sections.length === 0) {
        return;
    }

    function filterSettings() {
        const query = input.value.trim().toLowerCase();
        let visibleSections = 0;

        sections.forEach(section => {
            const items = Array.from(section.querySelectorAll('.row, .action-link, .warning-note'));
            const sectionText = section.innerText.toLowerCase();
            const headingText = Array.from(section.querySelectorAll('.section-head, h2')).map(item => item.innerText).join(' ').toLowerCase();
            const headingMatches = query !== '' && headingText.includes(query);
            let sectionMatches = query === '' || sectionText.includes(query);
            let visibleItems = 0;

            items.forEach(item => {
                const itemMatches = query === '' || headingMatches || item.innerText.toLowerCase().includes(query);
                item.style.display = itemMatches ? '' : 'none';
                if (itemMatches) {
                    visibleItems += 1;
                }
            });

            if (items.length === 0) {
                section.style.display = sectionMatches ? '' : 'none';
            } else {
                section.style.display = (sectionMatches && visibleItems > 0) ? '' : 'none';
            }

            if (section.style.display !== 'none') {
                visibleSections += 1;
            }
        });

        empty.style.display = visibleSections === 0 ? 'block' : 'none';
    }

    input.addEventListener('input', filterSettings);
})();

(function(){
    const enableButton = document.getElementById('enablePushCalls');
    const disableButton = document.getElementById('disablePushCalls');
    const status = document.getElementById('pushCallStatus');
    const container = document.getElementById('pushCallNotifications');
    const csrfInput = document.querySelector('input[name="csrf_token"]');
    const deviceStorageKey = 'ai_match_life_web_push_device_id';
    if (!enableButton || !disableButton || !status) return;
    const copy = container ? container.dataset : {};
    const text = (key, fallback) => copy[key] || fallback;

    function setStatus(message, busy) {
        status.textContent = message;
        enableButton.disabled = Boolean(busy);
        disableButton.disabled = Boolean(busy);
    }

    function decodeKey(value) {
        const padding = '='.repeat((4 - value.length % 4) % 4);
        const raw = atob((value + padding).replace(/-/g, '+').replace(/_/g, '/'));
        return Uint8Array.from(raw, character => character.charCodeAt(0));
    }

    function deviceId() {
        let value = localStorage.getItem(deviceStorageKey);
        if (!value) {
            const random = crypto.getRandomValues(new Uint8Array(16));
            value = 'web-' + Array.from(random, byte => byte.toString(16).padStart(2, '0')).join('');
            localStorage.setItem(deviceStorageKey, value);
        }
        return value;
    }

    async function registration() {
        return navigator.serviceWorker.register('/push-service-worker.js', { scope: '/' });
    }

    async function enablePush() {
        setStatus(text('enabling', 'Enabling…'), true);
        try {
            if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
                throw new Error(text('unsupported', 'Push notifications are not supported by this browser.'));
            }
            const configResponse = await fetch('/api/push/config', { credentials: 'same-origin' });
            const config = await configResponse.json();
            if (!configResponse.ok || !config.web_push || !config.web_push.configured) {
                throw new Error(text('notConfigured', 'Web Push is not configured on the server.'));
            }
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') throw new Error(text('permissionDenied', 'Notification permission was not granted.'));
            const worker = await registration();
            let subscription = await worker.pushManager.getSubscription();
            if (!subscription) {
                subscription = await worker.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: decodeKey(config.web_push.public_key),
                });
            }
            const response = await fetch('/api/push/devices', {
                method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfInput ? csrfInput.value : '' },
                body: JSON.stringify({
                    platform: 'web', device_id: deviceId(), token: JSON.stringify(subscription.toJSON()),
                    app_version: 'web', locale: navigator.language || '',
                }),
            });
            if (!response.ok) throw new Error(text('registrationFailed', 'Registration failed.'));
            setStatus(text('enabled', 'Incoming call notifications are enabled.'), false);
        } catch (error) {
            setStatus(error && error.message ? error.message : text('enableFailed', 'Could not enable notifications.'), false);
        }
    }

    async function disablePush() {
        setStatus(text('disabling', 'Disabling…'), true);
        try {
            const id = localStorage.getItem(deviceStorageKey);
            if (id) {
                const response = await fetch('/api/push/devices/' + encodeURIComponent(id), {
                    method: 'DELETE', credentials: 'same-origin',
                    headers: { 'X-CSRF-Token': csrfInput ? csrfInput.value : '' },
                });
                if (!response.ok) throw new Error(text('revokeFailed', 'Could not revoke this device.'));
            }
            const worker = await navigator.serviceWorker.getRegistration('/');
            const subscription = worker ? await worker.pushManager.getSubscription() : null;
            if (subscription) await subscription.unsubscribe();
            localStorage.removeItem(deviceStorageKey);
            setStatus(text('disabled', 'Incoming call notifications are disabled.'), false);
        } catch (error) {
            setStatus(error && error.message ? error.message : text('disableFailed', 'Could not disable notifications.'), false);
        }
    }

    enableButton.addEventListener('click', enablePush);
    disableButton.addEventListener('click', disablePush);
    if ('Notification' in window && Notification.permission === 'granted') setStatus(text('permissionActive', 'Notification permission is active.'), false);
    else if ('Notification' in window && Notification.permission === 'denied') setStatus(text('browserBlocked', 'Notifications are blocked in browser settings.'), false);
})();
