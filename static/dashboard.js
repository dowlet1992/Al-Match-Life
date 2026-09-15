(() => {
    "use strict";

    const avatarMenu = document.getElementById("heroAvatarMenu");
    const avatarMenuButton = document.getElementById("heroAvatarMenuButton");

    avatarMenuButton?.addEventListener("click", (event) => {
        event.stopPropagation();
        const isOpen = avatarMenu?.classList.toggle("open") ?? false;
        avatarMenuButton.setAttribute("aria-expanded", String(isOpen));
    });

    avatarMenu?.addEventListener("click", (event) => event.stopPropagation());

    document.addEventListener("click", () => {
        avatarMenu?.classList.remove("open");
        avatarMenuButton?.setAttribute("aria-expanded", "false");
    });

    document.addEventListener("change", (event) => {
        const fileInput = event.target.closest("input[type='file'][data-auto-submit]");
        if (!fileInput || !fileInput.files?.length) return;
        fileInput.form?.requestSubmit();
    });

    const composer = document.querySelector("[data-dashboard-composer]");
    const postText = composer?.querySelector("[data-post-text]");
    const postCounter = composer?.querySelector("[data-post-counter]");
    const postMedia = composer?.querySelector("[data-post-media]");
    const mediaSelection = composer?.querySelector("[data-media-selection]");
    const postSubmit = composer?.querySelector("[data-post-submit]");
    const submitLabel = postSubmit?.textContent.trim() || "Publish";

    function updateComposerState() {
        if (postCounter && postText) postCounter.textContent = `${postText.value.length} / 5000`;
        if (mediaSelection && postMedia) {
            const count = postMedia.files?.length || 0;
            mediaSelection.textContent = count ? Array.from(postMedia.files).slice(0, 3).map(file => file.name).join(", ") : "";
        }
    }
    postText?.addEventListener("input", updateComposerState);
    postMedia?.addEventListener("change", updateComposerState);
    composer?.addEventListener("submit", () => {
        if (!postSubmit) return;
        postSubmit.disabled = true;
        postSubmit.textContent = composer.dataset.publishingLabel || submitLabel;
    });
    updateComposerState();
})();
