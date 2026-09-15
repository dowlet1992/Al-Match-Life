(() => {
    "use strict";
    if (typeof window.__chatPageCleanup === 'function') window.__chatPageCleanup();
    const chatLifecycle = new AbortController();
    const chatIntervals = [];
    const repeatChatTask = function(callback, delay) {
        const timer = window.setInterval(callback, delay);
        chatIntervals.push(timer);
        return timer;
    };

    let activeIncomingCall = null;
    const chatConfig = document.getElementById('chatConfig').dataset;
    let CHAT_I18N = {};
    try {
        CHAT_I18N = JSON.parse(chatConfig.i18n || '{}');
    } catch (error) {
        console.warn('chat translations could not be loaded', error);
    }
    const chatCsrfToken = chatConfig.csrfToken || '';
    const chatSender = chatConfig.sender || '';
    const chatReceiver = chatConfig.receiver || '';
    const chatReceiverAvatar = chatConfig.receiverAvatar || '';
    const messageTranslationLanguage = chatConfig.translationLanguage || 'auto';
    const messageDraftKey = 'novix-chat-draft:' + chatSender.toLowerCase() + ':' + chatReceiver.toLowerCase();
    let draftSaveTimer = null;

    function setComposerStatus(text, state) {
        const status = document.getElementById('composerStatus');
        if (!status) return;
        status.textContent = text || '';
        status.dataset.state = state || '';
    }

    function updateComposerCounter() {
        const input = document.getElementById('messageInput');
        const counter = document.getElementById('composerCounter');
        if (input && counter) counter.textContent = input.value.length + ' / 2000';
    }

    function saveMessageDraft(showConfirmation) {
        const input = document.getElementById('messageInput');
        const editing = Boolean(document.getElementById('editMessageInput')?.value);
        if (!input || editing) return;
        try {
            const value = input.value;
            if (value.trim()) window.localStorage.setItem(messageDraftKey, value);
            else window.localStorage.removeItem(messageDraftKey);
            if (showConfirmation && value.trim() && navigator.onLine) setComposerStatus(CHAT_I18N.draftSaved, 'saved');
        } catch (error) {
            console.warn('message draft storage unavailable', error);
        }
    }

    function scheduleMessageDraftSave() {
        if (draftSaveTimer) window.clearTimeout(draftSaveTimer);
        draftSaveTimer = window.setTimeout(function() {
            draftSaveTimer = null;
            saveMessageDraft(true);
        }, 450);
    }

    function restoreMessageDraft() {
        const input = document.getElementById('messageInput');
        if (!input || input.value) return;
        try {
            const draft = window.localStorage.getItem(messageDraftKey) || '';
            if (!draft) return;
            input.value = draft.slice(0, 2000);
            updateComposerCounter();
            setComposerStatus(CHAT_I18N.draftRestored, 'restored');
        } catch (error) {
            console.warn('message draft restore unavailable', error);
        }
    }

    async function checkIncomingCall() {
        try {
            const response = await fetch('/pending_call/' + encodeURIComponent(chatSender) + '/' + encodeURIComponent(chatReceiver));
            const data = await response.json();
            const panel = document.getElementById('incomingCallPanel');
            if (!panel) return;

            if (!data.ok || !data.pending) {
                activeIncomingCall = null;
                panel.classList.remove('open');
                return;
            }

            activeIncomingCall = data;
            document.getElementById('incomingCallAvatar').src = data.caller_avatar || chatReceiverAvatar;
            document.getElementById('incomingCallTitle').innerText = data.call_type === 'video' ? CHAT_I18N.incomingVideoCall : CHAT_I18N.incomingAudioCall;
            document.getElementById('incomingCallSubtitle').innerText = (data.caller_name || CHAT_I18N.user) + ' ' + CHAT_I18N.isCallingYou;
            document.getElementById('incomingAcceptBtn').href = data.accept_url;
            panel.classList.add('open');
        } catch (error) {
            console.warn('incoming call check failed', error);
        }
    }

    async function declineIncomingCall() {
        if (!activeIncomingCall || !activeIncomingCall.decline_url) return;
        await fetch(activeIncomingCall.decline_url, { method: 'POST', headers: { 'X-CSRF-Token': chatCsrfToken } }).catch(function(error) { console.warn('decline failed', error); });
        const panel = document.getElementById('incomingCallPanel');
        if (panel) panel.classList.remove('open');
        activeIncomingCall = null;
    }

    checkIncomingCall();
    repeatChatTask(checkIncomingCall, 2500);

    const chatBox = document.getElementById('chatBox');
    if (chatBox) {
        chatBox.scrollTop = chatBox.scrollHeight;
        const fileInput = document.querySelector('input[name="media"]');
        const fileNameBox = document.getElementById('selectedFileName');

        if (fileInput && fileNameBox) {
            fileInput.addEventListener('change', function() {
                if (this.files.length > 0) {
                    fileNameBox.innerText = this.files[0].name;
                } else {
                    fileNameBox.innerText = '';
                }
            }, {signal: chatLifecycle.signal});
        }
    }

    function replyToMessage(messageId, text) {
        const replyBar = document.getElementById('replyBar');
        const replyText = document.getElementById('replyText');
        const replyToInput = document.getElementById('replyToInput');
        const messageInput = document.getElementById('messageInput');

        closeMessagePopups();
        replyToInput.value = messageId;
        replyText.innerText = text || CHAT_I18N.mediaFile;
        replyBar.style.display = 'block';
        messageInput.focus();
    }

    function cancelReply() {
        document.getElementById('replyToInput').value = '';
        document.getElementById('replyText').innerText = '';
        document.getElementById('replyBar').style.display = 'none';
    }

    function startEditMessage(messageId, text) {
        const editBar = document.getElementById('editBar');
        const editText = document.getElementById('editText');
        const editInput = document.getElementById('editMessageInput');
        const messageInput = document.getElementById('messageInput');
        const replyInput = document.getElementById('replyToInput');

        replyInput.value = '';
        document.getElementById('replyBar').style.display = 'none';

        closeMessagePopups();
        editInput.value = messageId;
        editText.innerText = text || CHAT_I18N.message;
        messageInput.value = text || '';
        editBar.style.display = 'block';
        messageInput.focus();
    }

    function cancelEdit() {
        document.getElementById('editMessageInput').value = '';
        document.getElementById('editText').innerText = '';
        document.getElementById('editBar').style.display = 'none';
        document.getElementById('messageInput').value = '';
    }

    let messageLongPressTimer = null;
    let messageLongPressTriggered = false;

    function closeMessagePopups() {
        document.querySelectorAll('.message-menu').forEach(menu => menu.classList.remove('open'));
        document.querySelectorAll('.reaction-menu').forEach(menu => menu.classList.remove('open'));
        document.querySelectorAll('.message-bubble').forEach(bubble => bubble.classList.remove('menu-open'));
        document.body.classList.remove('chat-focus-mode');
    }

    function toggleMessageMenu(messageId) {
        const currentMenu = document.getElementById('message-menu-' + messageId);
        const currentBubble = document.getElementById('message-' + messageId);
        if (!currentMenu || !currentBubble) return;

        const willOpen = !currentMenu.classList.contains('open');
        closeMessagePopups();

        if (willOpen) {
            document.body.classList.add('chat-focus-mode');
            currentBubble.classList.add('menu-open');

            if (currentMenu.parentElement !== document.body) {
                document.body.appendChild(currentMenu);
            }

            currentMenu.classList.add('open');

            const bubbleRect = currentBubble.getBoundingClientRect();
            const menuRect = currentMenu.getBoundingClientRect();
            const margin = 8;

            let left = bubbleRect.left;
            if (currentBubble.closest('.mine')) {
                left = bubbleRect.right - menuRect.width;
            }

            let top = bubbleRect.bottom + 6;

            if (left < margin) left = margin;
            if (left + menuRect.width > window.innerWidth - margin) {
                left = window.innerWidth - menuRect.width - margin;
            }

            if (top + menuRect.height > window.innerHeight - margin) {
                top = bubbleRect.top - menuRect.height - 6;
            }

            if (top < margin) top = margin;

            currentMenu.style.left = left + 'px';
            currentMenu.style.top = top + 'px';
        }
    }

    function toggleReactionMenu(messageId) {
        const currentReactionMenu = document.getElementById('reaction-menu-' + messageId);
        const currentBubble = document.getElementById('message-' + messageId);
        if (!currentReactionMenu || !currentBubble) return;

        const willOpen = !currentReactionMenu.classList.contains('open');
        closeMessagePopups();

        if (willOpen) {
            document.body.classList.add('chat-focus-mode');
            currentReactionMenu.classList.add('open');
            currentBubble.classList.add('menu-open');
        }
    }

    function startMessageLongPress(event, messageId) {
        if (
            event.target.closest('.message-menu') ||
            event.target.closest('.reaction-menu') ||
            event.target.closest('.message-select-check') ||
            event.target.closest('.menu-action') ||
            event.target.closest('.reaction-action')
        ) return;

        messageLongPressTriggered = false;
        clearTimeout(messageLongPressTimer);

        messageLongPressTimer = setTimeout(function() {
            messageLongPressTriggered = true;
            if (event && event.preventDefault) event.preventDefault();
            toggleMessageMenu(messageId);
        }, 300);

    }

    function cancelMessageLongPress() {
        clearTimeout(messageLongPressTimer);
    }

    function quickReactMessage(url) {
        window.location.href = url;
    }

    function pickReaction(event, element) {
        event.preventDefault();
        event.stopPropagation();

        if (!element || element.classList.contains('reaction-picked')) return;

        element.classList.add('reaction-picked');

        const menu = element.closest('.reaction-menu');
        const bubble = element.closest('.message-bubble');

        setTimeout(function() {
            if (menu) menu.classList.remove('open');
            if (bubble) bubble.classList.remove('menu-open');
            document.querySelectorAll('.message-menu').forEach(item => item.classList.remove('open'));
            document.body.classList.remove('chat-focus-mode');
        }, 180);

        setTimeout(function() {
            if (element.form) element.form.submit();
        }, 260);
    }

    let selectedMessageIds = [];
    let messageSelectionMode = false;

    function handleMessageClick(messageId) {
        if (messageLongPressTriggered) {
            messageLongPressTriggered = false;
            return;
        }

        if (typeof messageSelectionMode !== 'undefined' && messageSelectionMode) {
            toggleMessageSelected(messageId);
        }
    }

    function toggleMessageSelected(messageId) {
        const idText = String(messageId);
        const bubble = document.getElementById('message-' + idText);
        if (!bubble) return;

        if (!messageSelectionMode) {
            toggleMessageMenu(messageId);
            return;
        }

        if (selectedMessageIds.includes(idText)) {
            selectedMessageIds = selectedMessageIds.filter(item => item !== idText);
            bubble.classList.remove('selected-message');
        } else {
            selectedMessageIds.push(idText);
            bubble.classList.add('selected-message');
        }
    }

    function copyMessageText(text) {
        if (!text) return;
        navigator.clipboard.writeText(text);
    }

    async function translateChatMessage(messageId) {
        closeMessagePopups();
        const box = document.getElementById('translation-' + messageId);
        try {
            const response = await fetch('/api/chats/' + encodeURIComponent(chatReceiver) + '/messages/' + messageId + '/translation', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRF-Token': chatCsrfToken},
                body: JSON.stringify({target_language: messageTranslationLanguage})
            });
            const data = await response.json();
            if (!response.ok || !data.ok || !box) throw new Error('translation_unavailable');
            box.replaceChildren();
            const label = document.createElement('span');
            label.textContent = '🌐 ' + CHAT_I18N.translatedMessage;
            const text = document.createElement('p');
            text.textContent = data.translation.translated_text;
            box.append(label, text);
            box.hidden = false;
        } catch (error) {
            alert(CHAT_I18N.translationUnavailable);
        }
    }

    function scrollToMessage(messageId) {
        const message = document.getElementById('message-' + messageId);
        if (!message) return;
        message.scrollIntoView({ behavior: 'smooth', block: 'center' });
        message.style.outline = '2px solid #60a5fa';
        setTimeout(() => { message.style.outline = 'none'; }, 1500);
    }

    let chatSearchResults = [];
    let chatSearchIndex = -1;

    function toggleChatSearch() {
        const panel = document.getElementById('chatSearchPanel');
        const input = document.getElementById('chatSearchInput');
        if (!panel || !input) return;

        panel.classList.toggle('open');

        if (panel.classList.contains('open')) {
            setTimeout(() => input.focus(), 100);
        } else {
            clearChatSearch();
        }
    }

    function searchChatMessages() {
        const input = document.getElementById('chatSearchInput');
        const count = document.getElementById('chatSearchCount');
        const query = input ? input.value.trim().toLowerCase() : '';

        document.querySelectorAll('.message-bubble').forEach(bubble => {
            bubble.classList.remove('search-match');
            bubble.classList.remove('search-active');
        });

        chatSearchResults = [];
        chatSearchIndex = -1;

        if (!query) {
            if (count) count.innerText = CHAT_I18N.enterSearchText;
            return;
        }

        document.querySelectorAll('.message-bubble').forEach(bubble => {
            const text = bubble.innerText.toLowerCase();
            if (text.includes(query)) {
                bubble.classList.add('search-match');
                chatSearchResults.push(bubble);
            }
        });

        if (chatSearchResults.length === 0) {
            if (count) count.innerText = CHAT_I18N.searchNoResults;
            return;
        }

        chatSearchIndex = 0;
        activateSearchResult();
    }

    function activateSearchResult() {
        const count = document.getElementById('chatSearchCount');

        chatSearchResults.forEach(item => item.classList.remove('search-active'));

        if (chatSearchResults.length === 0 || chatSearchIndex < 0) return;

        const active = chatSearchResults[chatSearchIndex];
        active.classList.add('search-active');
        active.scrollIntoView({ behavior:'smooth', block:'center' });

        if (count) {
            count.innerText = CHAT_I18N.searchFound + ': ' + chatSearchResults.length + ' • ' + CHAT_I18N.searchCurrent + ': ' + (chatSearchIndex + 1) + '/' + chatSearchResults.length;
        }
    }

    function goToNextSearchResult() {
        if (chatSearchResults.length === 0) return;
        chatSearchIndex = (chatSearchIndex + 1) % chatSearchResults.length;
        activateSearchResult();
    }

    function goToPreviousSearchResult() {
        if (chatSearchResults.length === 0) return;
        chatSearchIndex = (chatSearchIndex - 1 + chatSearchResults.length) % chatSearchResults.length;
        activateSearchResult();
    }

    function clearChatSearch() {
        const panel = document.getElementById('chatSearchPanel');
        const input = document.getElementById('chatSearchInput');
        const count = document.getElementById('chatSearchCount');

        if (input) input.value = '';
        if (count) count.innerText = CHAT_I18N.enterSearchText;
        if (panel) panel.classList.remove('open');

        document.querySelectorAll('.message-bubble').forEach(bubble => {
            bubble.classList.remove('search-match');
            bubble.classList.remove('search-active');
        });

        chatSearchResults = [];
        chatSearchIndex = -1;
    }

    document.addEventListener('click', function(event) {
        if (!event.target.closest('.message-bubble')) {
            closeMessagePopups();
        }
    }, {signal: chatLifecycle.signal});

    // --- Incremental realtime chat transport ---
    let lastMessageId = Math.max(0, ...Array.from(document.querySelectorAll('.message-bubble[data-message-id]')).map(item => Number(item.dataset.messageId) || 0));
    let messageRequestRunning = false;

    function appendApiMessage(message, pending) {
        if (!chatBox || document.getElementById('message-' + message.id)) return;
        const nearBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < 140;
        const row = document.createElement('div');row.className='message-row '+(message.mine?'mine':'theirs');
        const bubble = document.createElement('div');bubble.className='message-bubble';bubble.id='message-'+message.id;
        bubble.dataset.messageId=String(message.id);bubble.dataset.messageText=message.message||'';bubble.dataset.messageTime=message.time||'';
        if (message.reply_to) {const reply=document.createElement('div');reply.className='reply-preview';reply.textContent='↩ '+message.reply_to;bubble.appendChild(reply)}
        if (message.media_url) {
            let media;
            if (message.media_type==='image') {media=document.createElement('img');media.className='chat-media-image';media.alt=''}
            else if (message.media_type==='video') {media=document.createElement('video');media.className='chat-media-video';media.controls=true}
            else if (message.media_type==='audio') {media=document.createElement('audio');media.controls=true}
            else {media=document.createElement('a');media.className='chat-document';media.textContent='📄 '+(message.media_name||'File');media.target='_blank';media.rel='noopener'}
            media.src=message.media_url;media.href=message.media_url;bubble.appendChild(media);
        }
        if (message.message) {const text=document.createElement('p');text.textContent=message.message;bubble.appendChild(text)}
        const meta=document.createElement('div');meta.className='message-meta';const time=document.createElement('span');time.textContent=message.time||'';meta.appendChild(time);
        if(message.mine){const delivery=document.createElement('span');delivery.className='message-delivery '+(pending?'pending-indicator':message.status==='read'?'read-indicator':'sent-indicator');delivery.textContent=pending?'◷':message.status==='read'?'✓✓':'✓';meta.appendChild(delivery)}
        bubble.appendChild(meta);row.appendChild(bubble);chatBox.appendChild(row);lastMessageId=Math.max(lastMessageId,Number(message.id)||0);if(nearBottom)chatBox.scrollTop=chatBox.scrollHeight;
    }

    function updateReadReceipts(readThroughId) {
        document.querySelectorAll('.message-row.mine .message-bubble').forEach(bubble=>{
            if((Number(bubble.dataset.messageId)||0)>readThroughId)return;const indicator=bubble.querySelector('.message-delivery');if(indicator){indicator.className='message-delivery read-indicator';indicator.textContent='✓✓'}
        });
    }

    async function refreshChatInBackground() {
        if(messageRequestRunning)return;messageRequestRunning=true;
        try {
            const response=await fetch('/api/chats/'+encodeURIComponent(chatReceiver)+'/messages?after_id='+lastMessageId+'&limit=100',{cache:'no-store'});const data=await response.json();
            if(!response.ok||!data.ok)return;data.messages.forEach(message=>appendApiMessage(message,false));updateReadReceipts(Number(data.peer_read_through_id)||0);
        } catch (error) {
            console.log('Chat refresh skipped');
        } finally {messageRequestRunning=false}
    }

    const messageInput = document.getElementById('messageInput');
    const messageForm = document.getElementById('messageForm');
    const micButton = document.getElementById('micButton');
    const audioDataInput = document.getElementById('audioDataInput');
    const voicePanel = document.getElementById('voicePanel');
    const voiceTimer = document.getElementById('voiceTimer');
    const voiceText = document.getElementById('voiceText');
    const cancelVoiceButton = document.getElementById('cancelVoiceButton');
    const sendVoiceButton = document.getElementById('sendVoiceButton');
    let mediaRecorder = null;
    let recordedChunks = [];
    let voiceStream = null;
    let recordingStartedAt = null;
    let recordingTimerInterval = null;
    let shouldSendVoice = false;

    function supportedVoiceFormat() {
        const formats = [
            {mimeType: 'audio/webm;codecs=opus', extension: 'webm'},
            {mimeType: 'audio/ogg;codecs=opus', extension: 'ogg'},
            {mimeType: 'audio/mp4', extension: 'm4a'}
        ];
        if (typeof MediaRecorder.isTypeSupported !== 'function') return null;
        return formats.find(format => MediaRecorder.isTypeSupported(format.mimeType)) || null;
    }

    async function uploadVoiceMessage(audioBlob, extension) {
        if (!messageForm || !audioBlob.size) throw new Error('empty voice recording');
        const formData = new FormData(messageForm);
        formData.delete('media');
        formData.set('message', '');
        formData.append('media', audioBlob, 'voice-message.' + extension);
        const response = await fetch(messageForm.action || window.location.href, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            headers: {'X-Requested-With': 'fetch'}
        });
        if (!response.ok) throw new Error('voice upload failed');
        resetVoiceUi();
        await refreshChatInBackground();
    }

    function formatVoiceTime(totalSeconds) {
        const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
        const seconds = Math.floor(totalSeconds % 60).toString().padStart(2, '0');
        return minutes + ':' + seconds;
    }

    function startVoiceTimer() {
        recordingStartedAt = Date.now();
        if (voiceTimer) voiceTimer.innerText = '00:00';
        recordingTimerInterval = setInterval(function() {
            const seconds = Math.floor((Date.now() - recordingStartedAt) / 1000);
            if (voiceTimer) voiceTimer.innerText = formatVoiceTime(seconds);
        }, 500);
    }

    function stopVoiceTimer() {
        if (recordingTimerInterval) {
            clearInterval(recordingTimerInterval);
            recordingTimerInterval = null;
        }
    }

    function resetVoiceUi() {
        stopVoiceTimer();
        if (voicePanel) voicePanel.style.display = 'none';
        if (voiceText) voiceText.innerText = CHAT_I18N.voiceRecording;
        if (voiceTimer) voiceTimer.innerText = '00:00';
        if (micButton) {
            micButton.classList.remove('recording');
            micButton.innerText = '🎤';
        }
    }

    function stopVoiceTracks() {
        if (voiceStream) {
            voiceStream.getTracks().forEach(track => track.stop());
            voiceStream = null;
        }
    }

    async function toggleVoiceRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert(CHAT_I18N.voiceNotSupported);
            return;
        }

        if (mediaRecorder && mediaRecorder.state === 'recording') {
            shouldSendVoice = false;
            mediaRecorder.stop();
            return;
        }

        try {
            voiceStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    channelCount: 1,
                    sampleRate: 48000
                }
            });
            recordedChunks = [];
            shouldSendVoice = false;
            const voiceFormat = supportedVoiceFormat();
            mediaRecorder = voiceFormat
                ? new MediaRecorder(voiceStream, {mimeType: voiceFormat.mimeType})
                : new MediaRecorder(voiceStream);

            mediaRecorder.ondataavailable = function(event) {
                if (event.data.size > 0) {
                    recordedChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = async function() {
                stopVoiceTimer();
                stopVoiceTracks();

                if (!shouldSendVoice) {
                    recordedChunks = [];
                    resetVoiceUi();
                    return;
                }

                const recordedType = (mediaRecorder.mimeType || recordedChunks[0]?.type || 'audio/webm').split(';', 1)[0];
                const extensionByType = {'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a'};
                const extension = extensionByType[recordedType] || 'webm';
                const audioBlob = new Blob(recordedChunks, {type: recordedType});
                try {
                    await uploadVoiceMessage(audioBlob, extension);
                } catch (error) {
                    resetVoiceUi();
                    alert(CHAT_I18N.voiceSendError || CHAT_I18N.microphoneError);
                }
            };

            mediaRecorder.start(250);
            startVoiceTimer();
            if (voicePanel) voicePanel.style.display = 'flex';
            micButton.classList.add('recording');
            micButton.innerText = '■';
        } catch (error) {
            resetVoiceUi();
            alert(CHAT_I18N.microphoneError);
        }
    }

    function cancelVoiceRecording() {
        shouldSendVoice = false;
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
        } else {
            resetVoiceUi();
            stopVoiceTracks();
        }
    }

    function sendVoiceRecording() {
        if (!mediaRecorder || mediaRecorder.state !== 'recording') return;
        shouldSendVoice = true;
        if (voiceText) voiceText.innerText = CHAT_I18N.voiceSending;
        mediaRecorder.stop();
    }

    if (micButton) {
        micButton.addEventListener('click', toggleVoiceRecording, {signal: chatLifecycle.signal});
    }

    if (cancelVoiceButton) {
        cancelVoiceButton.addEventListener('click', cancelVoiceRecording, {signal: chatLifecycle.signal});
    }

    if (sendVoiceButton) {
        sendVoiceButton.addEventListener('click', sendVoiceRecording, {signal: chatLifecycle.signal});
    }

    if (messageForm) messageForm.addEventListener('submit', async function(event) {
        const text=(messageInput?.value||'').trim();
        const hasFile=Boolean(document.getElementById('messageMediaInput')?.files?.length);
        const editing=Boolean(document.getElementById('editMessageInput')?.value);
        if(!text||hasFile||editing)return;
        event.preventDefault();
        const sendButton=messageForm.querySelector('.send-btn');if(sendButton)sendButton.disabled=true;
        const clientId=(window.crypto?.randomUUID?.()||('msg_'+Date.now()+'_'+Math.random().toString(36).slice(2))).replace(/-/g,'_');
        try {
            const response=await fetch('/api/chats/'+encodeURIComponent(chatReceiver)+'/messages',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':chatCsrfToken},body:JSON.stringify({message:text,reply_to:document.getElementById('replyToInput')?.value||'',client_message_id:clientId})});
            const data=await response.json();if(!response.ok||!data.ok)throw new Error('send_failed');
            appendApiMessage(data.message,false);messageInput.value='';cancelReply();messageInput.style.height='auto';saveMessageDraft(false);updateComposerCounter();setComposerStatus('', '');
        } catch(error){console.warn('message send failed', error);alert(CHAT_I18N.messageSendError||'Message could not be sent. Please try again.')} finally {if(sendButton)sendButton.disabled=false}
    }, {signal:chatLifecycle.signal});

    document.addEventListener('click', function(event) {
        const chatAction = event.target.closest('[data-chat-action]');
        if (chatAction && !event.target.closest('form')) {
            event.preventDefault();
            const action = chatAction.dataset.chatAction;
            if (action === 'scroll-message') scrollToMessage(chatAction.dataset.messageId);
            else if (action === 'toggle-search') toggleChatSearch();
            else if (action === 'decline-call') declineIncomingCall();
            else if (action === 'search-previous') goToPreviousSearchResult();
            else if (action === 'search-next') goToNextSearchResult();
            else if (action === 'search-clear') clearChatSearch();
            else if (action === 'cancel-reply') cancelReply();
            else if (action === 'cancel-edit') cancelEdit();
            return;
        }

        const actionButton = event.target.closest('[data-message-action]');
        if (actionButton) {
            event.preventDefault();
            event.stopPropagation();
            const container = actionButton.closest('[data-message-id]');
            const messageId = container ? container.dataset.messageId : '';
            const bubble = document.getElementById('message-' + messageId);
            const text = bubble ? bubble.dataset.messageText || '' : '';
            const action = actionButton.dataset.messageAction;
            if (action === 'select') toggleMessageSelected(messageId);
            else if (action === 'reply') replyToMessage(messageId, text);
            else if (action === 'edit') startEditMessage(messageId, text);
            else if (action === 'copy') copyMessageText(text);
            else if (action === 'translate') translateChatMessage(messageId);
            else if (action === 'info') alert(CHAT_I18N.sentAt + ' ' + (bubble?.dataset.messageTime || ''));
            return;
        }

        const reactionButton = event.target.closest('.reaction-action');
        if (reactionButton) pickReaction(event, reactionButton);

        const bubble = event.target.closest('.message-bubble');
        if (bubble && !event.target.closest('.message-menu,.reaction-menu')) {
            handleMessageClick(bubble.dataset.messageId);
        }
    }, {signal: chatLifecycle.signal});

    document.addEventListener('dblclick', function(event) {
        const bubble = event.target.closest('.message-bubble');
        if (!bubble || event.target.closest('button,a,form')) return;
        event.preventDefault();
        event.stopPropagation();
        toggleReactionMenu(bubble.dataset.messageId);
    }, {signal: chatLifecycle.signal});

    document.addEventListener('contextmenu', function(event) {
        const bubble = event.target.closest('.message-bubble');
        if (!bubble) return;
        event.preventDefault();
        event.stopPropagation();
        toggleMessageMenu(bubble.dataset.messageId);
    }, {signal: chatLifecycle.signal});

    document.addEventListener('pointerdown', function(event) {
        const bubble = event.target.closest('.message-bubble');
        if (bubble) startMessageLongPress(event, bubble.dataset.messageId);
    }, {signal: chatLifecycle.signal});
    document.addEventListener('pointerup', cancelMessageLongPress, {signal: chatLifecycle.signal});
    document.addEventListener('pointercancel', cancelMessageLongPress, {signal: chatLifecycle.signal});

    const chatSearchInput = document.getElementById('chatSearchInput');
    if (chatSearchInput) chatSearchInput.addEventListener('input', searchChatMessages, {signal: chatLifecycle.signal});

    function sendPresencePing() {
        fetch('/presence/' + encodeURIComponent(chatSender), { method: 'POST', headers: { 'X-CSRF-Token': chatCsrfToken } });
    }

    sendPresencePing();
    repeatChatTask(sendPresencePing, 10000);

    if (messageInput) {
        messageInput.addEventListener('input', function() {
            updateComposerCounter();
            scheduleMessageDraftSave();
            sendPresencePing();
            fetch('/typing/' + encodeURIComponent(chatSender) + '/' + encodeURIComponent(chatReceiver), {
                method: 'POST',
                headers: { 'X-CSRF-Token': chatCsrfToken }
            });
        }, {signal: chatLifecycle.signal});
    }

    window.addEventListener('offline', function() {
        saveMessageDraft(false);
        setComposerStatus(CHAT_I18N.offlineDraftSafe, 'offline');
    }, {signal: chatLifecycle.signal});
    window.addEventListener('online', function() {
        setComposerStatus(CHAT_I18N.connectionRestored, 'online');
        refreshChatInBackground();
    }, {signal: chatLifecycle.signal});

    restoreMessageDraft();
    updateComposerCounter();
    if (!navigator.onLine) setComposerStatus(CHAT_I18N.offlineDraftSafe, 'offline');

    repeatChatTask(refreshChatInBackground, 1500);

    window.__chatPageCleanup = function() {
        if (draftSaveTimer) window.clearTimeout(draftSaveTimer);
        saveMessageDraft(false);
        chatLifecycle.abort();
        chatIntervals.forEach(window.clearInterval);
        stopVoiceTimer();
        stopVoiceTracks();
    };
    document.addEventListener('app:navigation-before', window.__chatPageCleanup, {
        once: true,
        signal: chatLifecycle.signal
    });
})();
