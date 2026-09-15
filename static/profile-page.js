(() => {
    'use strict';

    async function copyProfileUrl(button, menu) {
        if (!navigator.clipboard) return;
        await navigator.clipboard.writeText(window.location.href);
        button.textContent = menu.dataset.copiedLabel || button.textContent;
    }

    document.addEventListener('click', async (event) => {
        const button = event.target.closest('[data-profile-action]');
        if (!button) return;
        const menu = button.closest('[data-profile-menu]');
        const action = button.dataset.profileAction;
        if (action === 'cancel') {
            menu?.removeAttribute('open');
            return;
        }
        if (action === 'copy') {
            await copyProfileUrl(button, menu);
            return;
        }
        if (action === 'share') {
            if (navigator.share) {
                await navigator.share({ title: document.title, url: window.location.href });
            } else {
                await copyProfileUrl(button, menu);
            }
        }
    });
})();
