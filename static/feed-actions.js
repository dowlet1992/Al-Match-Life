(() => {
    "use strict";

    const config = document.querySelector("[data-feed-actions]");
    const feedAutoplayEnabled = config?.dataset.autoplayEnabled === "true";
    const videoText = {
        paused: config?.dataset.videoPaused || "Paused",
        playing: config?.dataset.videoPlaying || "Playing",
        tapToPlay: config?.dataset.videoTapToPlay || "Tap ▶ to play",
    };

    function closePostMenus(except = null) {
        document.querySelectorAll(".post-action-menu").forEach((menu) => {
            if (menu !== except) menu.hidden = true;
        });
    }

    function togglePostMenu(button) {
        const menu = document.getElementById(button.dataset.menuId);
        if (!menu) return;
        const shouldOpen = menu.hidden || getComputedStyle(menu).display === "none";
        closePostMenus(menu);
        menu.hidden = !shouldOpen;
        menu.style.display = shouldOpen ? "block" : "none";
        button.setAttribute("aria-expanded", String(shouldOpen));
    }

    function toggleCommentBox(button) {
        const box = document.getElementById(`comment-box-${button.dataset.postId}`);
        if (!box) return;
        const shouldOpen = box.hidden || getComputedStyle(box).display === "none";
        box.hidden = !shouldOpen;
        box.style.display = shouldOpen ? "block" : "none";
        button.setAttribute("aria-expanded", String(shouldOpen));
        if (shouldOpen) box.querySelector("textarea")?.focus();
    }

    function setVideoStatus(video, text) {
        const status = video.parentElement?.querySelector(".feed-video-status");
        if (status) status.textContent = text;
    }

    function pauseAllFeedVideos(exceptVideo = null) {
        document.querySelectorAll(".feed-auto-video").forEach((video) => {
            if (video === exceptVideo) return;
            video.pause();
            video.dataset.userPaused = "false";
            setVideoStatus(video, videoText.paused);
        });
    }

    function playFeedVideo(video) {
        pauseAllFeedVideos(video);
        video.play()
            .then(() => setVideoStatus(video, videoText.playing))
            .catch(() => setVideoStatus(video, videoText.tapToPlay));
    }

    function toggleFeedVideo(video) {
        if (video.paused) {
            video.dataset.userPaused = "false";
            playFeedVideo(video);
        } else {
            video.dataset.userPaused = "true";
            video.pause();
            setVideoStatus(video, videoText.paused);
        }
    }

    document.addEventListener("click", (event) => {
        const menuButton = event.target.closest("[data-feed-action='menu']");
        if (menuButton) {
            event.stopPropagation();
            togglePostMenu(menuButton);
            return;
        }
        const commentButton = event.target.closest("[data-feed-action='comments']");
        if (commentButton) {
            toggleCommentBox(commentButton);
            return;
        }
        const soundButton = event.target.closest("[data-feed-action='sound']");
        if (soundButton) {
            event.stopPropagation();
            const video = soundButton.closest("div")?.querySelector(".feed-auto-video");
            if (video) {
                video.muted = !video.muted;
                soundButton.textContent = video.muted ? "🔇" : "🔊";
            }
            return;
        }
        const video = event.target.closest(".feed-auto-video");
        if (video) {
            toggleFeedVideo(video);
            return;
        }
        if (!event.target.closest(".post-action-menu")) closePostMenus();
    });

    const videos = document.querySelectorAll(".feed-auto-video");
    if (!videos.length) return;
    if (!feedAutoplayEnabled || !("IntersectionObserver" in window)) {
        videos.forEach((video) => {
            video.dataset.userPaused = "true";
            setVideoStatus(video, videoText.tapToPlay);
        });
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            const video = entry.target;
            if (entry.isIntersecting && entry.intersectionRatio >= 0.65) {
                if (video.dataset.userPaused !== "true") playFeedVideo(video);
            } else {
                video.pause();
                setVideoStatus(video, videoText.paused);
            }
        });
    }, {threshold: [0, 0.35, 0.65, 1]});

    videos.forEach((video) => {
        video.dataset.userPaused = "false";
        observer.observe(video);
    });
})();
