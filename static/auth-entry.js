(() => {
    'use strict';
    document.addEventListener('click', (event) => {
        const button = event.target.closest('[data-password-toggle]');
        if (!button) return;
        const input = document.getElementById('login-password');
        if (!input) return;
        const revealing = input.type === 'password';
        input.type = revealing ? 'text' : 'password';
        button.textContent = revealing ? '🙈' : '👁';
        button.setAttribute('aria-label', revealing ? button.dataset.hideLabel : button.dataset.showLabel);
    });
})();
