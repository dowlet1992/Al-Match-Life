(() => {
    'use strict';

    const state = window.__novixShell || {
        busy: false,
        navigationController: null,
        navigationSequence: 0,
        listenersInstalled: false,
    };
    window.__novixShell = state;
    const historyMarker = 'novix';

    function dashboardUrl() {
        const email = currentUser();
        return email ? `/dashboard/${encodeURIComponent(email)}` : '/';
    }

    function initializeHistory() {
        const existing = window.history.state || {};
        if (existing.app !== historyMarker) {
            window.history.replaceState(
                { ...existing, app: historyMarker, depth: 0 },
                '',
                window.location.href,
            );
        }
    }

    function languageText() {
        const copy = document.querySelector('.app-shell-nav')?.dataset || {};
        return {
            back: copy.copyBack || 'Back',
            failed: copy.copyFailed || 'The action could not be completed',
            groupCall: copy.copyGroupCall || 'Group call',
            join: copy.copyJoin || 'Join',
            decline: copy.copyDecline || 'Decline',
            invites: copy.copyInvites || 'invites you to a call',
        };
    }

    function currentUser() {
        return document.querySelector('meta[name="app-current-user"]')?.content || '';
    }

    function showToast(message) {
        document.querySelector('.app-shell-toast')?.remove();
        const toast = document.createElement('div');
        toast.className = 'app-shell-toast';
        toast.textContent = message;
        document.body.appendChild(toast);
        window.setTimeout(() => toast.remove(), 4000);
    }

    function initializeShell() {
        document.querySelector('.app-shell-back')?.remove();
        document.body.classList.remove('app-shell-active');

        const email = currentUser();
        if (!email || !document.querySelector('.app-shell-nav')) return;
        document.body.classList.add('app-shell-active');
        initializeBackControl();
        initializeConferenceInvites();
    }

    function initializeConferenceInvites() {
        if (state.conferenceInviteTimer || !currentUser() || /\/(audio_call|video_call|conference)\//.test(location.pathname)) return;
        const poll = async () => {
            try {
                const response = await fetch('/api/conferences/invitations', {cache:'no-store'});
                const data = await response.json();
                if (!response.ok || !data.ok || !data.invitations?.length) return;
                const invite = data.invitations[0];
                const seenKey = 'novix-conference-dismissed-' + invite.room_id;
                if (sessionStorage.getItem(seenKey) || document.querySelector('.conference-invite-banner')) return;
                showConferenceInvite(invite, seenKey);
            } catch (_error) { /* retry on next poll */ }
        };
        poll();
        state.conferenceInviteTimer = window.setInterval(poll, 4000);
    }

    function showConferenceInvite(invite, seenKey) {
        const copy = languageText();
        const banner = document.createElement('section');banner.className='conference-invite-banner';banner.setAttribute('role','dialog');
        const avatar=document.createElement('img');avatar.src=invite.caller_avatar||'/static/app-logo.svg';avatar.alt='';
        const text=document.createElement('div');const title=document.createElement('strong');title.textContent=copy.groupCall;
        const detail=document.createElement('span');detail.textContent=(invite.caller_name||'NOVIX')+' '+copy.invites;text.append(title,detail);
        const join=document.createElement('a');join.href=invite.join_url;join.textContent=copy.join;join.setAttribute('data-native','');
        const decline=document.createElement('button');decline.type='button';decline.textContent=copy.decline;
        decline.addEventListener('click',()=>{sessionStorage.setItem(seenKey,'1');banner.remove()});
        banner.append(avatar,text,join,decline);document.body.appendChild(banner);
    }

    function initializeBackControl() {
        const path = window.location.pathname;
        if (
            path.startsWith('/dashboard/')
            || path.startsWith('/audio_call/')
            || path.startsWith('/video_call/')
            || document.querySelector('[data-back], a.back, a.back-link')
        ) return;

        const target = document.querySelector('.page-main, main.main, main.page, .container');
        if (!target) return;
        const back = document.createElement('button');
        back.type = 'button';
        back.className = 'app-shell-back';
        back.setAttribute('data-back', '');
        back.innerHTML = '<span aria-hidden="true">←</span><span>' + languageText().back + '</span>';
        target.prepend(back);
    }

    function isCoreAsset(node) {
        const source = node.getAttribute('href') || node.getAttribute('src') || '';
        return source.endsWith('/static/app-shell.css')
            || source.endsWith('/static/app-shell.js');
    }

    function markInitialDynamicHead() {
        document.head.querySelectorAll('link[rel="stylesheet"], script[src]').forEach((node) => {
            if (!isCoreAsset(node)) node.setAttribute('data-dynamic-head', '');
        });
    }

    function syncHead(nextDocument) {
        document.title = nextDocument.title;
        document.querySelectorAll('[data-dynamic-head]').forEach((node) => node.remove());

        nextDocument.head.querySelectorAll('style, link[rel="stylesheet"]').forEach((node) => {
            if (isCoreAsset(node)) return;
            const clone = node.cloneNode(true);
            clone.setAttribute('data-dynamic-head', '');
            document.head.appendChild(clone);
        });

        document.querySelector('meta[name="app-current-user"]')?.remove();
        const nextUserMeta = nextDocument.querySelector('meta[name="app-current-user"]');
        if (nextUserMeta) document.head.appendChild(nextUserMeta.cloneNode(true));
        document.documentElement.lang = nextDocument.documentElement.lang || 'en';
        document.documentElement.dir = nextDocument.documentElement.dir || 'ltr';
    }

    function activateHeadScripts(nextDocument) {
        nextDocument.head.querySelectorAll('script[src]').forEach((sourceScript) => {
            if (isCoreAsset(sourceScript)) return;
            const script = document.createElement('script');
            for (const attribute of sourceScript.attributes) {
                if (attribute.name !== 'data-dynamic-head') {
                    script.setAttribute(attribute.name, attribute.value);
                }
            }
            script.async = false;
            script.setAttribute('data-dynamic-head', '');
            document.head.appendChild(script);
        });
    }

    function syncSidebar(nextDocument) {
        const currentSidebar = document.querySelector('.app-shell-nav');
        const nextSidebar = nextDocument.querySelector('.app-shell-nav');
        if (!nextSidebar) {
            currentSidebar?.remove();
            return null;
        }
        if (!currentSidebar) {
            const sidebar = document.importNode(nextSidebar, true);
            document.body.prepend(sidebar);
            return sidebar;
        }
        currentSidebar.replaceChildren(
            ...Array.from(nextSidebar.childNodes, (node) => document.importNode(node, true)),
        );
        for (const attribute of Array.from(currentSidebar.attributes)) {
            if (!nextSidebar.hasAttribute(attribute.name)) currentSidebar.removeAttribute(attribute.name);
        }
        for (const attribute of nextSidebar.attributes) {
            currentSidebar.setAttribute(attribute.name, attribute.value);
        }
        return currentSidebar;
    }

    function replacePageContent(nextDocument, preservedSidebar) {
        Array.from(document.body.childNodes).forEach((node) => {
            if (node !== preservedSidebar && !(node.nodeType === Node.ELEMENT_NODE && node.classList.contains('app-shell-toast'))) {
                node.remove();
            }
        });
        Array.from(nextDocument.body.childNodes).forEach((node) => {
            if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains('app-shell-nav')) return;
            document.body.appendChild(document.importNode(node, true));
        });
    }

    function activateScripts(root) {
        const nonce = document.querySelector('script[nonce]')?.nonce || '';
        root.querySelectorAll('script').forEach((oldScript) => {
            if ((oldScript.getAttribute('src') || '').endsWith('/static/app-shell.js')) {
                oldScript.remove();
                return;
            }
            const script = document.createElement('script');
            for (const attribute of oldScript.attributes) {
                if (attribute.name !== 'nonce') script.setAttribute(attribute.name, attribute.value);
            }
            if (nonce) script.setAttribute('nonce', nonce);
            script.textContent = oldScript.textContent;
            oldScript.replaceWith(script);
        });
    }

    function applyDocument(html, url, historyMode) {
        const nextDocument = new DOMParser().parseFromString(html, 'text/html');
        if (!nextDocument.body) throw new Error('Invalid HTML response');
        document.dispatchEvent(new CustomEvent('app:navigation-before', {detail: {url}}));
        syncHead(nextDocument);
        const sidebar = syncSidebar(nextDocument);
        replacePageContent(nextDocument, sidebar);
        document.body.className = nextDocument.body.className;
        initializeShell();
        activateScripts(document.body);
        activateHeadScripts(nextDocument);
        const currentDepth = Number(window.history.state?.depth || 0);
        if (historyMode === 'push') {
            window.history.pushState(
                { app: historyMarker, depth: currentDepth + 1 },
                '',
                url,
            );
        } else if (historyMode === 'replace') {
            window.history.replaceState(
                { app: historyMarker, depth: currentDepth },
                '',
                url,
            );
        }
        window.scrollTo({ top: 0, behavior: 'instant' });
        document.dispatchEvent(new CustomEvent('app:navigation-complete', { detail: { url } }));
    }

    async function navigate(url, options = {}, historyMode = 'push') {
        state.navigationController?.abort();
        const controller = new AbortController();
        const sequence = ++state.navigationSequence;
        state.navigationController = controller;
        document.documentElement.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(url, {
                credentials: 'same-origin',
                redirect: 'follow',
                ...options,
                signal: controller.signal,
                headers: {
                    'X-Requested-With': 'fetch',
                    ...(options.headers || {}),
                },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const contentType = response.headers.get('Content-Type') || '';
            if (!contentType.includes('text/html')) {
                document.dispatchEvent(new CustomEvent('app:action-complete', { detail: { response } }));
                return;
            }
            const finalUrl = response.url || url;
            applyDocument(await response.text(), finalUrl, historyMode);
        } catch (error) {
            if (error.name === 'AbortError') return;
            showToast(`${languageText().failed}: ${error.message || ''}`.trim());
        } finally {
            if (sequence === state.navigationSequence) {
                state.navigationController = null;
                document.documentElement.removeAttribute('aria-busy');
            }
        }
    }

    async function submitSocialFollow(form, submitter) {
        if (state.busy) return;
        state.busy = true;
        document.documentElement.setAttribute('aria-busy', 'true');
        if (submitter) submitter.disabled = true;
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const result = await response.json();
            if (!result.ok) throw new Error(result.error || 'Invalid response');
            form.action = result.next_action;
            if (submitter) {
                submitter.textContent = result.label;
                submitter.classList.toggle('primary', !result.is_following);
            }
            const followersCount = document.querySelector('[data-followers-stat] strong');
            if (followersCount) followersCount.textContent = String(result.followers_count);
            document.dispatchEvent(new CustomEvent('app:social-follow-changed', { detail: result }));
        } catch (error) {
            showToast(`${languageText().failed}: ${error.message || ''}`.trim());
        } finally {
            state.busy = false;
            document.documentElement.removeAttribute('aria-busy');
            if (submitter?.isConnected) submitter.disabled = false;
        }
    }

    async function submitFriendRequest(form, submitter) {
        if (state.busy) return;
        state.busy = true;
        document.documentElement.setAttribute('aria-busy', 'true');
        const card = form.closest('[data-friend-request-card]');
        card?.querySelectorAll('button').forEach((button) => { button.disabled = true; });
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const result = await response.json();
            if (!result.ok) throw new Error(result.error || 'Invalid response');
            if (card?.hasAttribute('data-remove-after-request')) {
                const list = card.closest('[data-friend-request-list]');
                card.remove();
                if (list && !list.querySelector('[data-friend-request-card]')) {
                    const empty = document.createElement('div');
                    empty.className = 'empty-state';
                    empty.textContent = list.dataset.emptyLabel || '';
                    list.appendChild(empty);
                }
            } else if (card) {
                card.querySelectorAll('[data-friend-request-action]').forEach((actionForm) => actionForm.remove());
                const actions = card.querySelector('.notification-actions');
                const status = document.createElement('span');
                status.className = `mini-status ${result.status}`;
                status.textContent = `${result.status === 'accepted' ? '✅' : '🚫'} ${result.label}`;
                actions?.appendChild(status);
            }
            document.dispatchEvent(new CustomEvent('app:friend-request-changed', { detail: result }));
        } catch (error) {
            showToast(`${languageText().failed}: ${error.message || ''}`.trim());
            card?.querySelectorAll('button').forEach((button) => { button.disabled = false; });
        } finally {
            state.busy = false;
            document.documentElement.removeAttribute('aria-busy');
            if (submitter?.isConnected) submitter.disabled = false;
        }
    }

    async function submitFeedMutation(form, submitter) {
        if (state.busy) return;
        state.busy = true;
        document.documentElement.setAttribute('aria-busy', 'true');
        if (submitter) submitter.disabled = true;
        const card = form.closest('[data-feed-post]');
        try {
            const response = await fetch(form.action, {
                method: 'POST', body: new FormData(form), credentials: 'same-origin',
                headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const result = await response.json();
            if (!result.ok) throw new Error(result.error || 'Invalid response');
            if (result.action === 'like') {
                const count = card?.querySelector('[data-feed-count="likes"]');
                if (count) count.textContent = String(result.likes_count);
                submitter?.classList.toggle('active', result.liked);
            } else if (result.action === 'save') {
                card?.querySelectorAll('[data-feed-count="saves"]').forEach((count) => { count.textContent = String(result.saves_count); });
                card?.querySelectorAll('[data-feed-mutation="save"] button').forEach((button) => { button.classList.toggle('active', result.saved); });
            } else if (result.action === 'comment') {
                const count = card?.querySelector('[data-feed-count="comments"]');
                if (count) count.textContent = String(result.comments_count);
                const list = card?.querySelector('.dashboard-comment-list');
                list?.querySelector('.dashboard-comments-empty')?.remove();
                if (list) {
                    const row = document.createElement('div');
                    row.className = 'dashboard-comment';
                    const author = document.createElement('strong');
                    author.textContent = result.comment.author_name;
                    row.append(author, document.createTextNode(`: ${result.comment.text}`));
                    list.appendChild(row);
                }
                form.reset();
            } else if (result.action === 'delete') {
                card?.remove();
            } else if (result.action === 'report') {
                if (submitter) {
                    submitter.textContent = `✓ ${submitter.textContent.replace(/^⚠️\s*/, '')}`;
                    submitter.disabled = true;
                }
            }
            document.dispatchEvent(new CustomEvent('app:feed-changed', { detail: result }));
        } catch (error) {
            showToast(`${languageText().failed}: ${error.message || ''}`.trim());
        } finally {
            state.busy = false;
            document.documentElement.removeAttribute('aria-busy');
            if (submitter?.isConnected) submitter.disabled = false;
        }
    }

    function installListeners() {
        if (state.listenersInstalled) return;
        state.listenersInstalled = true;

        document.addEventListener('click', (event) => {
            const back = event.target.closest('[data-back]');
            if (back) {
                event.preventDefault();
                const currentState = window.history.state;
                if (currentState?.app === historyMarker && Number(currentState.depth) > 0) {
                    window.history.back();
                } else {
                    navigate(dashboardUrl(), {}, 'replace');
                }
                return;
            }

            const link = event.target.closest('a[href]');
            if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            if (link.target || link.download || link.hasAttribute('data-native')) return;
            const url = new URL(link.href, window.location.href);
            if (url.origin !== window.location.origin || url.hash && url.pathname === window.location.pathname && url.search === window.location.search) return;
            if (/\/media-files\/|\/static\/|\/audio_call\/|\/video_call\//.test(url.pathname)) return;
            event.preventDefault();
            navigate(url.href);
        });

        document.addEventListener('submit', (event) => {
            const form = event.target.closest('form');
            if (!form || form.hasAttribute('data-native')) return;
            const action = new URL(form.action || window.location.href, window.location.href);
            if (action.origin !== window.location.origin) return;
            event.preventDefault();
            const submitter = event.submitter;
            if (form.hasAttribute('data-social-follow')) {
                submitSocialFollow(form, submitter);
                return;
            }
            if (form.hasAttribute('data-friend-request-action')) {
                submitFriendRequest(form, submitter);
                return;
            }
            if (form.hasAttribute('data-feed-mutation')) {
                submitFeedMutation(form, submitter);
                return;
            }
            if (submitter) submitter.disabled = true;
            const formData = new FormData(form);
            if (submitter?.name) formData.append(submitter.name, submitter.value);
            navigate(action.href, {
                method: (form.method || 'POST').toUpperCase(),
                body: formData,
            }).finally(() => {
                if (submitter?.isConnected) submitter.disabled = false;
            });
        });

        window.addEventListener('popstate', () => navigate(window.location.href, {}, 'none'));
    }

    markInitialDynamicHead();
    initializeHistory();
    installListeners();
    initializeShell();
})();
