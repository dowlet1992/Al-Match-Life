(() => {
    const form = document.querySelector('[data-ai-core-form]');
    if (!form) return;

    const button = form.querySelector('[data-ai-submit]');
    const stopButton = form.querySelector('[data-ai-stop]');
    const status = form.querySelector('[data-ai-loading]');
    let submitted = false;
    let requestController = null;
    let requestTimeout = null;
    let requestAbortReason = '';

    function stopGeneration() {
        requestAbortReason = 'user';
        if (requestController) requestController.abort();
    }

    if (stopButton) stopButton.addEventListener('click', stopGeneration);

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (submitted) {
            return;
        }
        submitted = true;
        requestAbortReason = '';
        requestController = new AbortController();
        requestTimeout = window.setTimeout(function() {
            requestAbortReason = 'timeout';
            if (requestController) requestController.abort();
        }, 120000);
        const label = form.dataset.loadingLabel || 'NOVIX is thinking…';
        if (button) {
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            button.textContent = label;
        }
        if (status) {
            status.hidden = false;
            status.textContent = label;
        }
        if (stopButton) stopButton.hidden = false;
        try {
            const formData = new FormData(form);
            const response = await fetch(form.action || window.location.href, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': String(formData.get('csrf_token') || '')
                },
                signal: requestController.signal,
                body: JSON.stringify({question: formData.get('question'), mode: formData.get('mode') || 'general'})
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error('assistant_unavailable');
            const answer = document.querySelector('[data-ai-answer]');
            if (answer) {
                const question = answer.querySelector('.ai-core-question');
                const text = answer.querySelector('.ai-core-answer-text');
                if (question) question.textContent = data.question;
                if (text) text.textContent = data.answer;
                answer.hidden = false;
                answer.scrollIntoView({behavior: 'smooth', block: 'start'});
            }
        } catch (error) {
            if (status) {
                const timedOut = requestAbortReason === 'timeout';
                status.textContent = error && error.name === 'AbortError'
                    ? (timedOut ? form.dataset.timeoutLabel : form.dataset.cancelledLabel)
                    : (form.dataset.errorLabel || 'The assistant is temporarily unavailable. Please try again.');
            }
            return;
        } finally {
            if (requestTimeout) window.clearTimeout(requestTimeout);
            requestTimeout = null;
            requestController = null;
            submitted = false;
            if (stopButton) stopButton.hidden = true;
            if (button) {
                button.disabled = false;
                button.removeAttribute('aria-busy');
                button.textContent = button.dataset.label || button.textContent;
            }
        }
        if (status) status.hidden = true;
    });

    if (button) button.dataset.label = button.textContent;
})();
