            let localStream = null;
            let screenShareTrack = null;
            let peerConnection = null;
            let speakerOn = true;
            let cameraFacing = 'user';
            let pollingTimer = null;
            let lastSignalTime = 0;
            let callStartedAt = null;
            let callTimer = null;
            let captionPollingTimer = null;
            let captionRecognition = null;
            let realtimeCaptionClient = null;
            let translatedSpeechPlaying = false;
            let translatedSpeechAudio = null;
            let translatedSpeechResolve = null;
            const translatedSpeechQueue = [];
            let captionsRunning = false;
            let lastCaptionTime = 0;
            let captionSequence = 0;
            let latestRemoteCaptionId = '';
            let serverCaptionRecorder = null;
            let serverCaptionTimer = null;
            let serverCaptionFailures = 0;
            let serverCaptionSuspended = false;
            let reconnectTimer = null;
            let reconnectAttempts = 0;
            let reconnectInProgress = false;
            let callStopping = false;
            const processedSignalIds = new Set();
            let localDescriptionPublished = false;
            let pendingLocalIceCandidates = [];
            const maxReconnectAttempts = 3;
            let qualityStatsTimer = null;
            let qualitySampleCount = 0;
            let previousInboundPackets = null;
            let previousOutboundBytes = null;
            let videoQualityLevel = 0;
            let consecutivePoorSamples = 0;
            let consecutiveGoodSamples = 0;
            const videoQualityProfiles = [
                {maxBitrate: 1500000, scaleResolutionDownBy: 1},
                {maxBitrate: 700000, scaleResolutionDownBy: 1.5},
                {maxBitrate: 300000, scaleResolutionDownBy: 2.5}
            ];
            const callConfig = document.getElementById('callConfig').dataset;
            let callI18n = {};
            try { callI18n = JSON.parse(callConfig.i18n || '{}'); } catch (_error) { callI18n = {}; }
            const t = function(key, fallback) { return callI18n[key] || fallback || key; };
            const configFlag = function(name) { return callConfig[name] === 'true'; };
            const needVideo = configFlag('needVideo');
            const isCaller = configFlag('isCaller');
            const captionsAllowed = configFlag('captionsAllowed');
            const serverTranscriptionAllowed = configFlag('serverTranscriptionAllowed');
            const realtimeTranscriptionAvailable = configFlag('realtimeTranscriptionAvailable');
            const aiVoiceTranslationAllowed = configFlag('aiVoiceTranslationAllowed');
            let aiVoiceTranslationEnabled = aiVoiceTranslationAllowed && configFlag('voiceTranslationEnabled');
            let autoTranslateCaptions = configFlag('autoTranslateCaptions');
            let captionTargetLanguage = callConfig.captionTargetLanguage || 'ru';
            let recognitionLanguage = callConfig.recognitionLanguage || '';
            const callId = callConfig.callId;
            const currentUser = callConfig.currentUser;
            const otherUser = callConfig.otherUser;
            const callType = callConfig.callType;
            const csrfToken = callConfig.csrfToken;
            const receiverName = callConfig.receiverName || '';
            const chatUrl = "/chat/" + encodeURIComponent(currentUser) + "/" + encodeURIComponent(otherUser);
            const signalingUrl = "/call_signal/" + encodeURIComponent(callId);
            const signalingAckUrl = signalingUrl + "/ack";
            const captionsUrl = "/api/calls/" + encodeURIComponent(callId) + "/captions";
            const iceServersUrl = "/api/calls/" + encodeURIComponent(callId) + "/ice-servers";
            const callQualityUrl = "/api/calls/" + encodeURIComponent(callId) + "/quality";
            const translationPreferencesUrl = "/api/calls/" + encodeURIComponent(callId) + "/translation/preferences";
            const fallbackIceServers = [{ urls: 'stun:stun.l.google.com:19302' }, { urls: 'stun:stun1.l.google.com:19302' }];
            let rtcConfig = { iceServers: fallbackIceServers };
            const speechLocales = {ru:'ru-RU', en:'en-US', de:'de-DE', it:'it-IT', es:'es-ES', fr:'fr-FR', pt:'pt-PT', tr:'tr-TR', uk:'uk-UA', pl:'pl-PL', nl:'nl-NL', hi:'hi-IN', id:'id-ID', ja:'ja-JP', ko:'ko-KR', zh:'zh-CN', ar:'ar-SA', ro:'ro-RO'};
            const speechLocale = code => speechLocales[code] || code || '';
            const audioConstraints = {
                echoCancellation: true, noiseSuppression: true, autoGainControl: true,
                channelCount: 1, sampleRate: 48000, sampleSize: 16
            };
            const videoConstraints = () => ({
                facingMode: cameraFacing,
                width: {ideal: 1280, max: 1920}, height: {ideal: 720, max: 1080},
                frameRate: {ideal: 24, max: 30}
            });

            function updateQualityIndicator(level) {
                const indicator = document.getElementById('callQuality');
                const label = document.getElementById('callQualityText');
                if (!indicator || !label) return;
                const labels = {
                    excellent: t('call_quality_excellent', 'Excellent connection'),
                    good: t('call_quality_good', 'Good connection'),
                    fair: t('call_quality_fair', 'Unstable connection'),
                    poor: t('call_quality_poor', 'Weak connection — prioritizing audio'),
                    offline: t('call_quality_offline', 'Offline')
                };
                indicator.dataset.level = level;
                label.textContent = labels[level] || t('connecting', 'Connecting');
            }

            function setStatus(text) {
                const status = document.getElementById('callStatus');
                const note = document.getElementById('callNote');
                if (status) status.innerText = text;
                if (note) note.innerText = text;
            }

            function setConnected() {
                const fallback = document.getElementById('remoteFallback');
                if (fallback) fallback.classList.add('connected');
                if (!callStartedAt) {
                    callStartedAt = Date.now();
                    callTimer = setInterval(function() {
                        const seconds = Math.floor((Date.now() - callStartedAt) / 1000);
                        const minutes = String(Math.floor(seconds / 60)).padStart(2, '0');
                        const rest = String(seconds % 60).padStart(2, '0');
                        setStatus(t('call_in_progress', 'Call in progress') + ' · ' + minutes + ':' + rest);
                    }, 1000);
                }
                if (!qualityStatsTimer) qualityStatsTimer = setInterval(collectCallQuality, 5000);
                const addParticipantButton = document.getElementById('addParticipantMenuBtn');
                if (addParticipantButton) addParticipantButton.disabled = false;
            }

            async function applyVideoQuality(level) {
                if (!needVideo || !peerConnection) return;
                const sender = peerConnection.getSenders().find(item => item.track && item.track.kind === 'video');
                if (!sender) return;
                const profile = videoQualityProfiles[Math.max(0, Math.min(level, videoQualityProfiles.length - 1))];
                try {
                    const parameters = sender.getParameters();
                    if (!parameters.encodings || !parameters.encodings.length) parameters.encodings = [{}];
                    parameters.encodings[0].maxBitrate = profile.maxBitrate;
                    parameters.encodings[0].scaleResolutionDownBy = profile.scaleResolutionDownBy;
                    await sender.setParameters(parameters);
                    videoQualityLevel = level;
                } catch (error) { console.warn('video quality adaptation failed', error); }
            }

            async function prioritizeSpeechAudio() {
                if (!peerConnection) return;
                const sender = peerConnection.getSenders().find(item => item.track && item.track.kind === 'audio');
                if (!sender) return;
                try {
                    const parameters = sender.getParameters();
                    if (!parameters.encodings || !parameters.encodings.length) parameters.encodings = [{}];
                    parameters.encodings[0].maxBitrate = 64000;
                    parameters.encodings[0].priority = 'high';
                    parameters.encodings[0].networkPriority = 'high';
                    await sender.setParameters(parameters);
                } catch (error) { console.warn('audio priority unavailable', error); }
            }

            async function collectCallQuality() {
                if (!peerConnection || peerConnection.connectionState !== 'connected' || callStopping) return;
                try {
                    const reports = await peerConnection.getStats();
                    let received = 0, lost = 0, jitterMs = 0, rttMs = 0, outboundBytes = 0, relay = false;
                    let selectedLocalCandidateId = '';
                    let reportTimestamp = Date.now();
                    reports.forEach(function(report) {
                        if (report.type === 'inbound-rtp' && !report.isRemote) {
                            received += Number(report.packetsReceived || 0);
                            lost += Number(report.packetsLost || 0);
                            jitterMs = Math.max(jitterMs, Number(report.jitter || 0) * 1000);
                        }
                        if (report.type === 'outbound-rtp' && !report.isRemote) {
                            outboundBytes += Number(report.bytesSent || 0);
                            reportTimestamp = Math.max(reportTimestamp, Number(report.timestamp || 0));
                        }
                        if (report.type === 'candidate-pair' && report.state === 'succeeded' && (report.nominated || report.selected)) {
                            rttMs = Math.max(rttMs, Number(report.currentRoundTripTime || 0) * 1000);
                            selectedLocalCandidateId = report.localCandidateId || selectedLocalCandidateId;
                        }
                    });
                    const selectedLocalCandidate = selectedLocalCandidateId ? reports.get(selectedLocalCandidateId) : null;
                    relay = Boolean(selectedLocalCandidate && selectedLocalCandidate.candidateType === 'relay');
                    let packetLossPercent = 0;
                    if (previousInboundPackets) {
                        const receivedDelta = Math.max(received - previousInboundPackets.received, 0);
                        const lostDelta = Math.max(lost - previousInboundPackets.lost, 0);
                        const totalDelta = receivedDelta + lostDelta;
                        if (totalDelta > 0) packetLossPercent = (lostDelta / totalDelta) * 100;
                    }
                    previousInboundPackets = {received: received, lost: lost};
                    let bitrateKbps = 0;
                    if (previousOutboundBytes && reportTimestamp > previousOutboundBytes.timestamp) {
                        bitrateKbps = Math.max((outboundBytes - previousOutboundBytes.bytes) * 8 / (reportTimestamp - previousOutboundBytes.timestamp), 0);
                    }
                    previousOutboundBytes = {bytes: outboundBytes, timestamp: reportTimestamp};
                    const poor = packetLossPercent >= 8 || rttMs >= 800 || jitterMs >= 80;
                    const good = packetLossPercent < 3 && rttMs < 350 && jitterMs < 35;
                    const qualityLevel = packetLossPercent >= 15 || rttMs >= 1200 || jitterMs >= 140
                        ? 'poor' : poor ? 'fair' : (packetLossPercent < 1.5 && rttMs < 180 && jitterMs < 20 ? 'excellent' : 'good');
                    updateQualityIndicator(qualityLevel);
                    consecutivePoorSamples = poor ? consecutivePoorSamples + 1 : 0;
                    consecutiveGoodSamples = good ? consecutiveGoodSamples + 1 : 0;
                    if (consecutivePoorSamples >= 2 && videoQualityLevel < videoQualityProfiles.length - 1) {
                        await applyVideoQuality(videoQualityLevel + 1);
                        consecutivePoorSamples = 0;
                    } else if (consecutiveGoodSamples >= 4 && videoQualityLevel > 0) {
                        await applyVideoQuality(videoQualityLevel - 1);
                        consecutiveGoodSamples = 0;
                    }
                    qualitySampleCount += 1;
                    if (qualitySampleCount % 3 === 0) {
                        fetch(callQualityUrl, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                            body: JSON.stringify({
                                other_email: otherUser, call_type: callType, rtt_ms: rttMs,
                                jitter_ms: jitterMs, packet_loss_percent: packetLossPercent,
                                bitrate_kbps: bitrateKbps, relay: relay
                            })
                        }).catch(function(error) { console.warn('quality sample failed', error); });
                    }
                } catch (error) { console.warn('WebRTC stats unavailable', error); }
            }

            async function loadIceConfiguration() {
                try {
                    const query = '?other_email=' + encodeURIComponent(otherUser) + '&call_type=' + encodeURIComponent(callType);
                    const response = await fetch(iceServersUrl + query, {cache: 'no-store'});
                    const data = await response.json();
                    if (response.ok && data.ok && Array.isArray(data.ice_servers) && data.ice_servers.length) {
                        rtcConfig = {iceServers: data.ice_servers};
                        if (data.provider !== 'twilio') console.warn('TURN relay unavailable; using STUN fallback');
                    }
                } catch (error) {
                    console.warn('ICE configuration unavailable; using STUN fallback', error);
                }
            }

            async function sendSignal(type, payload) {
                const eventId = window.crypto && typeof window.crypto.randomUUID === 'function'
                    ? window.crypto.randomUUID()
                    : ('evt_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 14));
                const requestBody = JSON.stringify({
                    event_id: eventId,
                    type: type,
                    from: currentUser,
                    to: otherUser,
                    payload: Object.assign({ call_type: callType }, payload || {})
                });
                for (let attempt = 0; attempt < 3; attempt += 1) {
                    try {
                        const response = await fetch(signalingUrl, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
                            body: requestBody
                        });
                        const data = await response.json().catch(function() { return {}; });
                        if (response.ok && data.ok && data.event_id === eventId) return true;
                        if (response.status < 500) return false;
                    } catch (error) {
                        console.warn('signal send failed', error);
                    }
                    if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 300 * Math.pow(2, attempt)));
                }
                return false;
            }

            async function publishLocalDescription(type, description) {
                localDescriptionPublished = false;
                const published = await sendSignal(type, description);
                if (!published) return false;
                localDescriptionPublished = true;
                const queued = pendingLocalIceCandidates.splice(0);
                for (const candidate of queued) await sendSignal('ice', candidate);
                return true;
            }

            async function acknowledgeSignalDelivery(eventIds) {
                const uniqueIds = Array.from(new Set(eventIds.filter(Boolean))).slice(0, 50);
                if (!uniqueIds.length) return true;
                const body = JSON.stringify({other_email: otherUser, call_type: callType, event_ids: uniqueIds});
                for (let attempt = 0; attempt < 3; attempt += 1) {
                    try {
                        const response = await fetch(signalingAckUrl, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                            body: body
                        });
                        if (response.ok) return true;
                        if (response.status < 500 && response.status !== 429) return false;
                    } catch (error) { console.warn('signal acknowledgment failed', error); }
                    if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 250 * Math.pow(2, attempt)));
                }
                return false;
            }

            function clearReconnectState() {
                if (reconnectTimer) clearTimeout(reconnectTimer);
                reconnectTimer = null;
                reconnectAttempts = 0;
                reconnectInProgress = false;
            }

            async function finishLostConnection() {
                if (callStopping) return;
                callStopping = true;
                setStatus(t('call_reconnect_failed', 'The connection could not be restored. The call has ended.'));
                if (navigator.onLine) {
                    await sendSignal('ended', {
                        ended_at: new Date().toISOString(),
                        reason: 'connection_lost',
                        call_type: needVideo ? 'video' : 'audio'
                    });
                }
                stopEverything();
                window.setTimeout(function() { window.location.href = chatUrl; }, 900);
            }

            function scheduleReconnect(delayMs) {
                if (callStopping || !peerConnection || peerConnection.connectionState === 'connected') return;
                if (reconnectTimer) clearTimeout(reconnectTimer);
                reconnectTimer = setTimeout(attemptReconnect, Math.max(Number(delayMs) || 0, 0));
            }

            async function attemptReconnect() {
                reconnectTimer = null;
                if (callStopping || !peerConnection || peerConnection.connectionState === 'connected') return;
                if (!navigator.onLine) {
                    setStatus(t('offline_waiting', 'Offline. Waiting for the connection to return…'));
                    scheduleReconnect(5000);
                    return;
                }
                if (reconnectAttempts >= maxReconnectAttempts) {
                    await finishLostConnection();
                    return;
                }
                reconnectAttempts += 1;
                reconnectInProgress = true;
                setStatus(t('reconnecting_attempt', 'Restoring connection · attempt') + ' ' + reconnectAttempts + '/' + maxReconnectAttempts);
                if (isCaller) {
                    try {
                        if (peerConnection.signalingState === 'stable') {
                            if (typeof peerConnection.restartIce === 'function') peerConnection.restartIce();
                            const restartOffer = await peerConnection.createOffer({iceRestart: true});
                            localDescriptionPublished = false;
                            await peerConnection.setLocalDescription(restartOffer);
                            await publishLocalDescription('offer', restartOffer);
                        }
                    } catch (error) {
                        console.warn('ICE restart failed', error);
                    }
                }
                scheduleReconnect(Math.min(4000 * reconnectAttempts, 10000));
            }

            function showCaption(label, text) {
                const panel = document.getElementById('captionPanel');
                const labelBox = document.getElementById('captionLabel');
                const textBox = document.getElementById('captionText');
                if (panel) panel.classList.add('open');
                if (labelBox) labelBox.textContent = label;
                if (textBox) textBox.textContent = text;
                const translationRow = document.getElementById('captionTranslationRow');
                if (translationRow) translationRow.hidden = true;
                setCaptionState('');
            }

            function setCaptionState(text) {
                const stateBox = document.getElementById('captionState');
                if (stateBox) stateBox.textContent = text || '';
            }

            function showTranslatedCaption(speaker, originalText, translatedText) {
                const panel = document.getElementById('captionPanel');
                const originalLabel = document.getElementById('captionLabel');
                const original = document.getElementById('captionText');
                const translationRow = document.getElementById('captionTranslationRow');
                const translationLabel = document.getElementById('captionTranslationLabel');
                const translation = document.getElementById('captionTranslationText');
                if (panel) panel.classList.add('open');
                if (originalLabel) originalLabel.textContent = speaker;
                if (original) original.textContent = originalText || '';
                if (translationLabel) translationLabel.textContent = t('translation_label', 'Translation') + ' · ' + captionTargetLanguage.toUpperCase();
                if (translation) translation.textContent = translatedText || '';
                if (translationRow) translationRow.hidden = false;
                setCaptionState('');
            }

            async function publishCaption(text, isFinal) {
                if (!text || !captionsRunning) return;
                captionSequence += 1;
                await fetch(captionsUrl, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                    body: JSON.stringify({
                        other_email: otherUser, call_type: callType, text: text,
                        source_language: recognitionLanguage || 'unknown', is_final: Boolean(isFinal), sequence: captionSequence
                    })
                }).catch(function(error) { console.warn('caption publish failed', error); });
            }

            async function startRealtimeCaptions() {
                if (!serverTranscriptionAllowed || !realtimeTranscriptionAvailable || !window.RealtimeCaptionClient || !localStream) return false;
                realtimeCaptionClient = new window.RealtimeCaptionClient({
                    createSession: async function() {
                        const response = await fetch('/api/calls/' + encodeURIComponent(callId) + '/translation/realtime-session', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                            body: JSON.stringify({other_email: otherUser, call_type: callType, source_language: recognitionLanguage || 'auto'})
                        });
                        const data = await response.json();
                        if (!response.ok || !data.ok) throw new Error(data.error || 'realtime_session_failed');
                        return data.session;
                    },
                    onPartial: text => { if (captionsRunning) showCaption(t('you', 'You') + ' · AI', text); },
                    onFinal: text => {
                        if (!captionsRunning) return;
                        showCaption(t('you', 'You') + ' · AI', text);
                        publishCaption(text, true);
                    },
                    onError: error => console.warn('realtime captions provider error', error),
                    onState: state => console.debug('realtime captions state', state)
                });
                try {
                    await realtimeCaptionClient.start(localStream);
                    return true;
                } catch (error) {
                    console.warn('realtime captions unavailable; using fallback', error);
                    realtimeCaptionClient.stop();
                    realtimeCaptionClient = null;
                    return false;
                }
            }

            function preferredCaptionMimeType() {
                const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
                return candidates.find(type => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || '';
            }

            function startServerCaptionCycle() {
                if (!captionsRunning || serverCaptionSuspended || !localStream || !window.MediaRecorder) return;
                const audioTracks = localStream.getAudioTracks();
                if (!audioTracks.length) return;
                const mimeType = preferredCaptionMimeType();
                const chunks = [];
                try {
                    serverCaptionRecorder = mimeType
                        ? new MediaRecorder(new MediaStream(audioTracks), {mimeType: mimeType})
                        : new MediaRecorder(new MediaStream(audioTracks));
                } catch (error) {
                    showCaption(t('live_captions', 'Live captions'), t('server_transcription_unavailable', 'Server transcription is unavailable in this browser.'));
                    return;
                }
                serverCaptionRecorder.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data); };
                serverCaptionRecorder.onstop = async function() {
                    if (!captionsRunning || !chunks.length) return;
                    const blob = new Blob(chunks, {type: serverCaptionRecorder.mimeType || mimeType || 'audio/webm'});
                    const form = new FormData();
                    form.append('other_email', otherUser);
                    form.append('call_type', callType);
                    form.append('source_language', recognitionLanguage || 'unknown');
                    form.append('sequence', String(++captionSequence));
                    form.append('audio', blob, 'caption-chunk');
                    try {
                        const response = await fetch(captionsUrl + '/transcribe', {
                            method: 'POST', headers: {'X-CSRF-Token': csrfToken}, body: form
                        });
                        const data = await response.json();
                        if (response.ok && data.ok) {
                            serverCaptionFailures = 0;
                            if (captionsRunning) showCaption(t('you', 'You'), data.caption.text || '');
                        } else if (response.status === 429) {
                            const retrySeconds = Math.max(Number(response.headers.get('Retry-After') || 4), 1);
                            serverCaptionTimer = setTimeout(startServerCaptionCycle, retrySeconds * 1000);
                            return;
                        } else if (response.status === 409 && data.error === 'Duplicate audio chunk') {
                            console.warn('duplicate caption chunk ignored');
                        } else {
                            serverCaptionFailures += 1;
                            if (response.status < 500 || serverCaptionFailures >= 3) {
                                serverCaptionSuspended = true;
                                showCaption(t('live_captions', 'Live captions'), t('server_transcription_paused', 'Server transcription is paused. The other participant’s captions will continue.'));
                                return;
                            }
                            const retryDelay = Math.min(2000 * Math.pow(2, serverCaptionFailures - 1), 8000);
                            serverCaptionTimer = setTimeout(startServerCaptionCycle, retryDelay);
                            return;
                        }
                    } catch (error) {
                        serverCaptionFailures += 1;
                        console.warn('server transcription failed', error);
                        if (serverCaptionFailures >= 3) {
                            serverCaptionSuspended = true;
                            showCaption(t('live_captions', 'Live captions'), t('server_transcription_connection_error', 'Server transcription is paused. Check your connection.'));
                            return;
                        }
                        serverCaptionTimer = setTimeout(startServerCaptionCycle, Math.min(2000 * Math.pow(2, serverCaptionFailures - 1), 8000));
                        return;
                    }
                    if (captionsRunning && !serverCaptionSuspended) startServerCaptionCycle();
                };
                serverCaptionRecorder.start();
                serverCaptionTimer = setTimeout(function() {
                    if (serverCaptionRecorder && serverCaptionRecorder.state === 'recording') serverCaptionRecorder.stop();
                }, 2500);
            }

            async function pollCaptions() {
                if (!captionsRunning) return;
                try {
                    const query = '?other_email=' + encodeURIComponent(otherUser) + '&call_type=' + encodeURIComponent(callType) + '&after=' + encodeURIComponent(lastCaptionTime);
                    const response = await fetch(captionsUrl + query);
                    const data = await response.json();
                    for (const caption of data.captions || []) {
                        if (caption.created_at) lastCaptionTime = Math.max(lastCaptionTime, Number(caption.created_at));
                        latestRemoteCaptionId = caption.id || '';
                        showCaption(receiverName, caption.text || '');
                        if (autoTranslateCaptions && caption.is_final && latestRemoteCaptionId) translateRemoteCaption(caption);
                    }
                } catch (error) { console.warn('caption poll failed', error); }
            }

            async function translateRemoteCaption(caption) {
                const captionId = caption.id || '';
                if (caption.source_language && caption.source_language !== 'unknown' && caption.source_language === captionTargetLanguage) {
                    setCaptionState('');
                    return;
                }
                try {
                    setCaptionState(t('call_translating', 'Translating…'));
                    const response = await fetch(captionsUrl + '/' + encodeURIComponent(captionId) + '/translation', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                        body: JSON.stringify({other_email: otherUser, call_type: callType, target_language: captionTargetLanguage})
                    });
                    const data = await response.json();
                    if (response.ok && data.ok && latestRemoteCaptionId === captionId) {
                        const translatedText = data.translation.translated_text || caption.text || '';
                        showTranslatedCaption(receiverName, caption.text || '', translatedText);
                        if (aiVoiceTranslationEnabled) enqueueTranslatedSpeech(captionId, translatedText, data.translation.target_language || captionTargetLanguage);
                    }
                } catch (error) {
                    setCaptionState('');
                    console.warn('caption translation failed', error);
                }
            }

            function enqueueTranslatedSpeech(captionId, text, language) {
                if (!captionId || !text || translatedSpeechQueue.some(item => item.id === captionId)) return;
                translatedSpeechQueue.push({id: captionId, text: text, language: language || captionTargetLanguage});
                while (translatedSpeechQueue.length > 2) translatedSpeechQueue.shift();
                playNextTranslatedSpeech();
            }

            function speakOnDevice(text, language) {
                if (!window.speechSynthesis || typeof window.SpeechSynthesisUtterance !== 'function') {
                    return Promise.reject(new Error('device_speech_unavailable'));
                }
                return new Promise((resolve, reject) => {
                    const utterance = new SpeechSynthesisUtterance(text);
                    utterance.lang = speechLocale(language || captionTargetLanguage || document.documentElement.lang || '');
                    utterance.rate = 1;
                    utterance.pitch = 1;
                    utterance.onend = resolve;
                    utterance.onerror = reject;
                    window.speechSynthesis.speak(utterance);
                });
            }

            async function playNextTranslatedSpeech() {
                if (translatedSpeechPlaying || !captionsRunning || !translatedSpeechQueue.length) return;
                translatedSpeechPlaying = true;
                const speechItem = translatedSpeechQueue.shift();
                const captionId = speechItem.id;
                let objectUrl = '';
                const remoteMedia = document.getElementById('remoteVideo') || document.getElementById('remoteAudio');
                const previousVolume = remoteMedia ? remoteMedia.volume : 1;
                try {
                    setCaptionState(t('call_speaking_translation', 'Playing translated speech…'));
                    const response = await fetch(captionsUrl + '/' + encodeURIComponent(captionId) + '/speech', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                        body: JSON.stringify({other_email: otherUser, call_type: callType, voice: 'coral', target_language: captionTargetLanguage})
                    });
                    if (!response.ok || response.headers.get('X-AI-Generated-Voice') !== 'true') throw new Error('translated_speech_failed');
                    const audioBlob = await response.blob();
                    objectUrl = URL.createObjectURL(audioBlob);
                    const audio = new Audio(objectUrl);
                    translatedSpeechAudio = audio;
                    if (remoteMedia) remoteMedia.volume = Math.min(previousVolume, 0.28);
                    await new Promise((resolve, reject) => {
                        translatedSpeechResolve = resolve;
                        audio.onended = resolve;
                        audio.onerror = reject;
                        audio.play().catch(reject);
                    });
                } catch (error) {
                    try {
                        await speakOnDevice(speechItem.text, speechItem.language);
                    } catch (deviceError) {
                        console.warn('translated speech unavailable', error, deviceError);
                    }
                } finally {
                    if (remoteMedia) remoteMedia.volume = previousVolume;
                    if (objectUrl) URL.revokeObjectURL(objectUrl);
                    translatedSpeechAudio = null;
                    translatedSpeechResolve = null;
                    translatedSpeechPlaying = false;
                    setCaptionState('');
                    if (captionsRunning) playNextTranslatedSpeech();
                }
            }

            function stopTranslatedSpeech() {
                translatedSpeechQueue.length = 0;
                if (translatedSpeechAudio) translatedSpeechAudio.pause();
                if (translatedSpeechResolve) translatedSpeechResolve();
                if (window.speechSynthesis) window.speechSynthesis.cancel();
            }

            function toggleTranslationPanel() {
                const panel = document.getElementById('translationPanel');
                if (!panel) return;
                panel.hidden = !panel.hidden;
                const button = document.getElementById('translationSettingsBtn');
                button?.classList.toggle('off', !panel.hidden);
                button?.setAttribute('aria-expanded', String(!panel.hidden));
            }

            function initializeTranslationSettings() {
                const source = document.getElementById('callSourceLanguage');
                const target = document.getElementById('callTargetLanguage');
                const translateToggle = document.getElementById('callTranslateCaptions');
                const voiceToggle = document.getElementById('callVoiceTranslation');
                try {
                    const saved = JSON.parse(window.localStorage.getItem('novix-call-translation') || '{}');
                    if (saved.source) recognitionLanguage = saved.source === 'auto' ? '' : saved.source;
                    if (saved.target) captionTargetLanguage = saved.target;
                    if (typeof saved.translate === 'boolean') autoTranslateCaptions = saved.translate;
                    if (typeof saved.voice === 'boolean') aiVoiceTranslationEnabled = aiVoiceTranslationAllowed && saved.voice;
                } catch (_error) { /* use server defaults */ }
                if (source) source.value = recognitionLanguage || 'auto';
                if (target && target.querySelector('option[value="' + CSS.escape(captionTargetLanguage) + '"]')) target.value = captionTargetLanguage;
                if (translateToggle) translateToggle.checked = autoTranslateCaptions;
                if (voiceToggle) voiceToggle.checked = aiVoiceTranslationEnabled;
            }

            async function applyTranslationSettings() {
                const sourceValue = document.getElementById('callSourceLanguage')?.value || 'auto';
                const targetValue = document.getElementById('callTargetLanguage')?.value || document.documentElement.lang || 'en';
                const previousSource = recognitionLanguage;
                recognitionLanguage = sourceValue === 'auto' ? '' : sourceValue;
                captionTargetLanguage = targetValue;
                autoTranslateCaptions = Boolean(document.getElementById('callTranslateCaptions')?.checked);
                aiVoiceTranslationEnabled = aiVoiceTranslationAllowed && Boolean(document.getElementById('callVoiceTranslation')?.checked);
                window.localStorage.setItem('novix-call-translation', JSON.stringify({
                    source: sourceValue, target: captionTargetLanguage,
                    translate: autoTranslateCaptions, voice: aiVoiceTranslationEnabled
                }));
                let preferencesSaved = false;
                try {
                    const response = await fetch(translationPreferencesUrl, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                        body: JSON.stringify({
                            other_email: otherUser, call_type: callType,
                            source_language: sourceValue, target_language: captionTargetLanguage,
                            translate_captions: autoTranslateCaptions,
                            voice_translation: aiVoiceTranslationEnabled
                        })
                    });
                    const result = await response.json().catch(function() { return {}; });
                    preferencesSaved = response.ok && result.ok === true;
                } catch (error) {
                    console.warn('translation preference sync failed', error);
                }
                document.getElementById('translationPanel').hidden = true;
                document.getElementById('translationSettingsBtn')?.classList.remove('off');
                document.getElementById('translationSettingsBtn')?.setAttribute('aria-expanded', 'false');
                stopTranslatedSpeech();
                if (captionsRunning && previousSource !== recognitionLanguage) {
                    await toggleCaptions();
                    await toggleCaptions();
                } else if (!captionsRunning && captionsAllowed && autoTranslateCaptions) {
                    await toggleCaptions();
                }
                showCaption(
                    t('translation_label', 'Translation'),
                    preferencesSaved
                        ? t('call_translation_saved', 'Translation settings saved to your account')
                        : t('call_translation_local_only', 'Translation is active on this device; sync is unavailable')
                );
            }

            async function toggleCaptions() {
                if (!captionsAllowed) {
                    showCaption(
                        'CC',
                        t('captions_disabled_help', 'Captions are disabled. Enable them in Settings → Privacy.')
                    );
                    return;
                }
                const button = document.getElementById('captionsBtn');
                if (captionsRunning) {
                    captionsRunning = false;
                    if (captionRecognition) captionRecognition.stop();
                    if (realtimeCaptionClient) realtimeCaptionClient.stop();
                    realtimeCaptionClient = null;
                    stopTranslatedSpeech();
                    if (captionPollingTimer) clearInterval(captionPollingTimer);
                    if (serverCaptionTimer) clearTimeout(serverCaptionTimer);
                    if (serverCaptionRecorder && serverCaptionRecorder.state === 'recording') serverCaptionRecorder.stop();
                    if (button) button.classList.remove('off');
                    return;
                }
                captionsRunning = true;
                if (button) button.classList.add('off');
                captionPollingTimer = setInterval(pollCaptions, 800);
                pollCaptions();
                if (await startRealtimeCaptions()) return;
                const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                if (!Recognition || !recognitionLanguage) {
                    serverCaptionFailures = 0;
                    serverCaptionSuspended = false;
                    if (!serverTranscriptionAllowed) {
                        showCaption(t('live_captions', 'Live captions'), t('local_recognition_unavailable', 'Local recognition is unavailable. Allow server transcription in settings to process short audio fragments.'));
                        return;
                    }
                    startServerCaptionCycle();
                    return;
                }
                captionRecognition = new Recognition();
                if (recognitionLanguage) captionRecognition.lang = speechLocale(recognitionLanguage);
                captionRecognition.continuous = true;
                captionRecognition.interimResults = true;
                captionRecognition.onresult = function(event) {
                    let interim = '';
                    for (let index = event.resultIndex; index < event.results.length; index += 1) {
                        const transcript = event.results[index][0].transcript.trim();
                        if (event.results[index].isFinal) {
                            showCaption(t('you', 'You'), transcript);
                            publishCaption(transcript, true);
                        } else { interim += transcript + ' '; }
                    }
                    if (interim.trim()) showCaption(t('you', 'You'), interim.trim());
                };
                captionRecognition.onerror = function(event) {
                    if (event.error !== 'aborted') showCaption(t('live_captions', 'Live captions'), t('speech_recognition_unavailable', 'Speech recognition is temporarily unavailable.'));
                };
                captionRecognition.onend = function() {
                    if (captionsRunning) { try { captionRecognition.start(); } catch (error) { console.warn('caption restart failed', error); } }
                };
                captionRecognition.start();
            }

            async function pollSignals() {
                try {
                    const response = await fetch(signalingUrl + '?other=' + encodeURIComponent(otherUser) + '&call_type=' + encodeURIComponent(callType) + '&after=' + encodeURIComponent(lastSignalTime));
                    const data = await response.json();

                    // Keep a one-second overlap so a concurrent write between the room read and
                    // the response watermark cannot be skipped; message IDs make the overlap safe.
                    if (data.server_time) lastSignalTime = Math.max(lastSignalTime, Number(data.server_time) - 1);

                    const deliveryAcks = [];
                    for (const message of data.messages || []) {
                        if (message.created_at) lastSignalTime = Math.max(lastSignalTime, Number(message.created_at));
                        if (message.id && processedSignalIds.has(message.id)) {
                            deliveryAcks.push(message.id);
                            continue;
                        }
                        await handleSignal(message);
                        if (message.id) {
                            processedSignalIds.add(message.id);
                            deliveryAcks.push(message.id);
                            if (processedSignalIds.size > 600) {
                                const oldestId = processedSignalIds.values().next().value;
                                processedSignalIds.delete(oldestId);
                            }
                        }
                    }
                    await acknowledgeSignalDelivery(deliveryAcks);
                    if (data.status === 'ended' || data.status === 'declined' || data.status === 'missed') {
                        stopEverything();
                        window.location.href = chatUrl;
                        return;
                    }
                } catch (error) {
                    console.warn('signal poll failed', error);
                }
            }

            async function handleSignal(message) {
                if (!peerConnection) return;
                const type = message.type;
                const payload = message.payload || {};

                if (type === 'offer') {
                    setStatus(t('connecting', 'Connecting…'));
                    if (peerConnection.signalingState !== 'stable' && peerConnection.signalingState === 'have-local-offer') {
                        await peerConnection.setLocalDescription({type: 'rollback'});
                    }
                    await peerConnection.setRemoteDescription(new RTCSessionDescription(payload));
                    const answer = await peerConnection.createAnswer();
                    await peerConnection.setLocalDescription(answer);
                    await publishLocalDescription('answer', answer);
                } else if (type === 'answer') {
                    if (!peerConnection.currentRemoteDescription) {
                        await peerConnection.setRemoteDescription(new RTCSessionDescription(payload));
                    }
                } else if (type === 'ice') {
                    if (payload && payload.candidate) {
                        await peerConnection.addIceCandidate(new RTCIceCandidate(payload)).catch(function(error) { console.warn('ice failed', error); });
                    }
                } else if (type === 'conference_upgrade' && payload.room_id) {
                    stopEverything();
                    window.location.href = '/conference/' + encodeURIComponent(payload.room_id);
                }
            }

            let participantDirectory = [];

            function toggleCallMenu(forceOpen) {
                const menu = document.getElementById('callMoreMenu');
                const button = document.getElementById('callMoreBtn');
                if (!menu || !button) return;
                const open = typeof forceOpen === 'boolean' ? forceOpen : menu.hidden;
                menu.hidden = !open;
                button.setAttribute('aria-expanded', String(open));
            }

            function closeParticipantPicker() {
                const picker = document.getElementById('participantPicker');
                if (picker) picker.hidden = true;
            }

            function renderParticipantDirectory(query) {
                const list = document.getElementById('participantList');
                const empty = document.getElementById('participantEmpty');
                if (!list || !empty) return;
                const normalizedQuery = String(query || '').trim().toLocaleLowerCase();
                const people = participantDirectory.filter(function(person) {
                    return !normalizedQuery || String(person.name || '').toLocaleLowerCase().includes(normalizedQuery);
                });
                list.replaceChildren();
                people.forEach(function(person) {
                    const row = document.createElement('article'); row.className = 'participant-person';
                    const avatar = document.createElement('img'); avatar.src = person.avatar || '/static/app-logo.svg'; avatar.alt = '';
                    const name = document.createElement('strong'); name.textContent = person.name || person.email;
                    const invite = document.createElement('button'); invite.type = 'button'; invite.textContent = '+';
                    invite.setAttribute('aria-label', t('add_people', 'Add people') + ': ' + name.textContent);
                    invite.addEventListener('click', function() { addParticipantToCall(person, invite); });
                    row.append(avatar, name, invite); list.appendChild(row);
                });
                empty.hidden = people.length > 0;
            }

            async function openParticipantPicker() {
                if (!peerConnection || peerConnection.connectionState !== 'connected') return;
                toggleCallMenu(false);
                const picker = document.getElementById('participantPicker');
                if (picker) picker.hidden = false;
                try {
                    const response = await fetch('/api/conferences/eligible?exclude=' + encodeURIComponent(otherUser), {cache: 'no-store'});
                    const data = await response.json();
                    if (!response.ok || !data.ok) throw new Error(data.error || 'contacts_unavailable');
                    participantDirectory = Array.isArray(data.people) ? data.people : [];
                    renderParticipantDirectory(document.getElementById('participantSearch')?.value || '');
                    document.getElementById('participantSearch')?.focus();
                } catch (error) {
                    console.warn('conference contacts unavailable', error);
                    closeParticipantPicker();
                    setStatus(t('conference_unavailable', 'Group call is temporarily unavailable'));
                }
            }

            async function addParticipantToCall(person, button) {
                if (!person || !person.email) return;
                if (button) button.disabled = true;
                try {
                    const response = await fetch('/api/conferences', {
                        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                        body: JSON.stringify({call_type: callType, participants: [otherUser, person.email]})
                    });
                    const data = await response.json();
                    if (!response.ok || !data.ok) throw new Error(data.error || 'conference_create_failed');
                    const delivered = await sendSignal('conference_upgrade', {call_type: callType, room_id: data.room_id});
                    if (!delivered) throw new Error('conference_upgrade_failed');
                    stopEverything();
                    window.location.href = data.join_url;
                } catch (error) {
                    console.warn('group conference unavailable', error);
                    setStatus(t('conference_unavailable', 'Group call is temporarily unavailable'));
                    if (button) button.disabled = false;
                }
            }

            async function startCall() {
                try {
                    setStatus(t('requesting_media_access', 'Requesting camera and microphone access…'));
                    if (localStream) localStream.getTracks().forEach(track => track.stop());

                    const constraints = needVideo
                        ? {audio: audioConstraints, video: videoConstraints()}
                        : {audio: audioConstraints, video: false};
                    localStream = await navigator.mediaDevices.getUserMedia(constraints);
                    localStream.getAudioTracks().forEach(track => { track.contentHint = 'speech'; });
                    localStream.getVideoTracks().forEach(track => { track.contentHint = 'motion'; });
                    await loadIceConfiguration();

                    const localVideo = document.getElementById('localVideo');
                    if (localVideo) localVideo.srcObject = localStream;

                    peerConnection = new RTCPeerConnection(rtcConfig);

                    localStream.getTracks().forEach(function(track) {
                        peerConnection.addTrack(track, localStream);
                    });
                    await prioritizeSpeechAudio();

                    peerConnection.ontrack = function(event) {
                        const remoteStream = event.streams[0];
                        const remoteVideo = document.getElementById('remoteVideo');
                        const remoteAudio = document.getElementById('remoteAudio');
                        if (remoteVideo) remoteVideo.srcObject = remoteStream;
                        if (remoteAudio) remoteAudio.srcObject = remoteStream;
                        setConnected();
                    };

                    peerConnection.onicecandidate = function(event) {
                        if (!event.candidate) return;
                        if (!localDescriptionPublished) pendingLocalIceCandidates.push(event.candidate);
                        else sendSignal('ice', event.candidate);
                    };

                    peerConnection.onconnectionstatechange = function() {
                        if (!peerConnection) return;
                        const state = peerConnection.connectionState;
                        if (state === 'connected') {
                            clearReconnectState();
                            setConnected();
                        }
                        if (state === 'failed') scheduleReconnect(0);
                        if (state === 'disconnected') {
                            setStatus(t('connection_interrupted', 'Connection interrupted. Trying to restore it…'));
                            scheduleReconnect(5000);
                        }
                        if (state === 'closed') setStatus(t('call_ended', 'Call ended'));
                    };

                    if (isCaller) {
                        setStatus(t('waiting_for_answer', 'Calling… Waiting for an answer.'));
                        await sendSignal('ringing', { call_type: needVideo ? 'video' : 'audio' });

                        const offer = await peerConnection.createOffer();
                        await peerConnection.setLocalDescription(offer);
                        await publishLocalDescription('offer', offer);
                    } else {
                        setStatus(t('joining_incoming_call', 'Joining incoming call…'));
                        await sendSignal('accepted', { accepted_at: new Date().toISOString(), call_type: needVideo ? 'video' : 'audio' });
                    }

                    pollingTimer = setInterval(pollSignals, 1000);
                    await pollSignals();
                } catch (error) {
                    console.error(error);
                    setStatus(t('media_access_denied', 'Camera or microphone access is unavailable.'));
                    alert(t('media_access_denied', 'Camera or microphone access is unavailable.'));
                }
            }

            function toggleMute() {
                const muteBtn = document.getElementById('muteBtn');
                const muteIcon = document.getElementById('muteIcon');
                if (!localStream) return;
                localStream.getAudioTracks().forEach(function(track) {
                    track.enabled = !track.enabled;
                    if (track.enabled) {
                        if (muteBtn) muteBtn.classList.remove('off');
                        if (muteIcon) muteIcon.innerText = '🎙️';
                    } else {
                        if (muteBtn) muteBtn.classList.add('off');
                        if (muteIcon) muteIcon.innerText = '🔇';
                    }
                });
            }

            function toggleCamera() {
                const cameraBtn = document.getElementById('cameraBtn');
                if (!localStream) return;
                localStream.getVideoTracks().forEach(function(track) {
                    track.enabled = !track.enabled;
                    if (track.enabled) { if (cameraBtn) cameraBtn.classList.remove('off'); }
                    else { if (cameraBtn) cameraBtn.classList.add('off'); }
                });
            }

            function toggleSpeaker() {
                const speakerBtn = document.getElementById('speakerBtn');
                const speakerIcon = document.getElementById('speakerIcon');
                speakerOn = !speakerOn;
                const mediaElements = [document.getElementById('remoteVideo'), document.getElementById('remoteAudio')].filter(Boolean);
                mediaElements.forEach(function(element) { element.muted = !speakerOn; });
                if (speakerOn) {
                    if (speakerBtn) speakerBtn.classList.remove('off');
                    if (speakerIcon) speakerIcon.innerText = '🔊';
                } else {
                    if (speakerBtn) speakerBtn.classList.add('off');
                    if (speakerIcon) speakerIcon.innerText = '🔈';
                }
            }

            async function flipCamera() {
                if (!needVideo || !localStream || !peerConnection) return;
                cameraFacing = cameraFacing === 'user' ? 'environment' : 'user';
                const newStream = await navigator.mediaDevices.getUserMedia({audio: false, video: videoConstraints()});
                const newVideoTrack = newStream.getVideoTracks()[0];
                if (!newVideoTrack) return;
                if (newVideoTrack) newVideoTrack.contentHint = 'motion';
                const oldVideoTrack = localStream.getVideoTracks()[0];
                if (oldVideoTrack) oldVideoTrack.stop();
                if (oldVideoTrack) localStream.removeTrack(oldVideoTrack);
                localStream.addTrack(newVideoTrack);
                const senderTrack = peerConnection.getSenders().find(item => item.track && item.track.kind === 'video');
                if (senderTrack && !screenShareTrack) await senderTrack.replaceTrack(newVideoTrack);
                const localVideo = document.getElementById('localVideo');
                if (localVideo && !screenShareTrack) localVideo.srcObject = localStream;
            }

            function updateScreenShareButton(active) {
                const button = document.getElementById('screenShareBtn');
                if (!button) return;
                button.classList.toggle('off', active);
                button.setAttribute('aria-pressed', String(active));
                const label = button.querySelector('span');
                if (label) label.textContent = active
                    ? t('stop_sharing_screen', 'Stop sharing')
                    : t('share_screen', 'Share screen');
            }

            async function stopScreenShare() {
                const activeTrack = screenShareTrack;
                if (!activeTrack) return;
                screenShareTrack = null;
                activeTrack.onended = null;
                const cameraTrack = localStream && localStream.getVideoTracks()[0];
                const sender = peerConnection && peerConnection.getSenders().find(item => item.track && item.track.kind === 'video');
                try {
                    if (sender && cameraTrack) await sender.replaceTrack(cameraTrack);
                } catch (error) {
                    console.warn('camera restore failed', error);
                }
                activeTrack.stop();
                const localVideo = document.getElementById('localVideo');
                if (localVideo && localStream) localVideo.srcObject = localStream;
                updateScreenShareButton(false);
                setStatus(t('screen_share_stopped', 'Screen sharing stopped'));
            }

            async function toggleScreenShare() {
                if (!needVideo || !localStream || !peerConnection) return;
                if (screenShareTrack) {
                    await stopScreenShare();
                    return;
                }
                if (!navigator.mediaDevices || typeof navigator.mediaDevices.getDisplayMedia !== 'function') {
                    setStatus(t('screen_share_unavailable', 'Screen sharing is unavailable in this browser'));
                    return;
                }
                try {
                    const displayStream = await navigator.mediaDevices.getDisplayMedia({
                        video: {frameRate: {ideal: 15, max: 30}},
                        audio: false
                    });
                    const displayTrack = displayStream.getVideoTracks()[0];
                    if (!displayTrack) return;
                    const sender = peerConnection.getSenders().find(item => item.track && item.track.kind === 'video');
                    if (!sender) {
                        displayTrack.stop();
                        return;
                    }
                    await sender.replaceTrack(displayTrack);
                    screenShareTrack = displayTrack;
                    displayTrack.contentHint = 'detail';
                    displayTrack.onended = function() { stopScreenShare(); };
                    const localVideo = document.getElementById('localVideo');
                    if (localVideo) localVideo.srcObject = displayStream;
                    updateScreenShareButton(true);
                    setStatus(t('screen_share_active', 'You are sharing your screen'));
                } catch (error) {
                    if (error && error.name !== 'NotAllowedError') console.warn('screen share failed', error);
                    updateScreenShareButton(false);
                }
            }

            function stopEverything() {
                callStopping = true;
                if (screenShareTrack) {
                    screenShareTrack.onended = null;
                    screenShareTrack.stop();
                    screenShareTrack = null;
                }
                if (pollingTimer) clearInterval(pollingTimer);
                if (callTimer) clearInterval(callTimer);
                if (qualityStatsTimer) clearInterval(qualityStatsTimer);
                if (reconnectTimer) clearTimeout(reconnectTimer);
                if (captionPollingTimer) clearInterval(captionPollingTimer);
                if (serverCaptionTimer) clearTimeout(serverCaptionTimer);
                captionsRunning = false;
                if (captionRecognition) captionRecognition.stop();
                if (realtimeCaptionClient) realtimeCaptionClient.stop();
                realtimeCaptionClient = null;
                stopTranslatedSpeech();
                if (serverCaptionRecorder && serverCaptionRecorder.state === 'recording') serverCaptionRecorder.stop();
                if (localStream) localStream.getTracks().forEach(track => track.stop());
                if (peerConnection) peerConnection.close();
                localStream = null;
                peerConnection = null;
            }

            async function endCall() {
                if (callStopping) return;
                callStopping = true;
                await sendSignal('ended', { ended_at: new Date().toISOString(), call_type: needVideo ? 'video' : 'audio' });
                stopEverything();
                window.location.href = chatUrl;
            }

            window.addEventListener('beforeunload', function() {
                if (localStream) localStream.getTracks().forEach(track => track.stop());
            });
            window.addEventListener('offline', function() {
                updateQualityIndicator('offline');
                if (!callStopping) {
                    setStatus(t('offline_call_recovery', 'Offline. The call will resume when the connection returns…'));
                    scheduleReconnect(5000);
                }
            });
            window.addEventListener('online', function() {
                if (!callStopping && peerConnection && peerConnection.connectionState !== 'connected') {
                    scheduleReconnect(0);
                }
            });
            const callActions = {
                mute: toggleMute,
                speaker: toggleSpeaker,
                camera: toggleCamera,
                flip: flipCamera,
                'screen-share': toggleScreenShare,
                captions: toggleCaptions,
                'translation-settings': toggleTranslationPanel,
                end: endCall
            };
            document.querySelectorAll('[data-call-action]').forEach(function(button) {
                button.addEventListener('click', function() {
                    const action = callActions[button.dataset.callAction];
                    if (action) {
                        action();
                        if (button.closest('.call-more-menu')) toggleCallMenu(false);
                    }
                });
            });
            document.getElementById('closeTranslationPanel')?.addEventListener('click', toggleTranslationPanel);
            document.getElementById('applyTranslationSettings')?.addEventListener('click', applyTranslationSettings);
            document.getElementById('callMoreBtn')?.addEventListener('click', function(event) { event.stopPropagation(); toggleCallMenu(); });
            document.getElementById('addParticipantMenuBtn')?.addEventListener('click', openParticipantPicker);
            document.getElementById('closeParticipantPicker')?.addEventListener('click', closeParticipantPicker);
            document.getElementById('participantSearch')?.addEventListener('input', function(event) { renderParticipantDirectory(event.target.value); });
            document.getElementById('participantPicker')?.addEventListener('click', function(event) { if (event.target === event.currentTarget) closeParticipantPicker(); });
            document.addEventListener('click', function(event) { if (!event.target.closest('.call-top-actions')) toggleCallMenu(false); });
            document.addEventListener('keydown', function(event) { if (event.key === 'Escape') { toggleCallMenu(false); closeParticipantPicker(); } });
            initializeTranslationSettings();
            startCall();
