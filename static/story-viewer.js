(() => {
    'use strict';

    function initializeStoryViewer(root) {
        if (!root || root.dataset.initialized === 'true') return;
        root.dataset.initialized = 'true';

        const slides = Array.from(root.querySelectorAll('.story-slide'));
        const fills = Array.from(root.querySelectorAll('.story-progress-fill'));
        const backUrl = root.dataset.backUrl || '/';
        const duration = 5000;
        let current = 0;
        let timer;

        function close() {
            window.location.assign(backUrl);
        }

        function show(index) {
            if (index < 0) index = 0;
            if (index >= slides.length) {
                close();
                return;
            }

            slides.forEach((slide, slideIndex) => {
                slide.classList.toggle('active', slideIndex === index);
                const video = slide.querySelector('video');
                if (!video) return;
                if (slideIndex === index) {
                    video.currentTime = 0;
                    video.play().catch(() => {});
                } else {
                    video.pause();
                }
            });

            fills.forEach((fill, fillIndex) => {
                fill.style.transition = 'none';
                fill.style.width = fillIndex < index ? '100%' : '0';
            });

            current = index;
            window.clearTimeout(timer);
            window.requestAnimationFrame(() => {
                fills[current].style.transition = `width ${duration}ms linear`;
                fills[current].style.width = '100%';
            });
            timer = window.setTimeout(() => show(current + 1), duration);
        }

        root.querySelector('[data-story-previous]')?.addEventListener('click', () => show(current - 1));
        root.querySelector('[data-story-next]')?.addEventListener('click', () => show(current + 1));
        document.addEventListener('keydown', (event) => {
            if (!root.isConnected) return;
            if (event.key === 'ArrowRight') show(current + 1);
            if (event.key === 'ArrowLeft') show(current - 1);
            if (event.key === 'Escape') close();
        });
        show(0);
    }

    const initialize = () => initializeStoryViewer(document.querySelector('[data-story-viewer]'));
    document.addEventListener('app:navigation-complete', initialize);
    initialize();
})();
