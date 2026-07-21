(function (global) {
    'use strict';

    class RealtimeCaptionClient {
        constructor(options) {
            this.options = options || {};
            this.peer = null;
            this.channel = null;
            this.audioTrack = null;
            this.running = false;
            this.partialByItem = new Map();
        }

        async start(stream) {
            if (this.running) return;
            if (!stream || !global.RTCPeerConnection || !global.FormData) {
                throw new Error('realtime_webrtc_unsupported');
            }
            const sourceTrack = stream.getAudioTracks()[0];
            if (!sourceTrack) throw new Error('realtime_audio_track_missing');
            const session = await this.options.createSession();
            if (!session || !session.client_secret || !session.calls_endpoint) {
                throw new Error('invalid_realtime_session');
            }
            const peer = new global.RTCPeerConnection();
            const channel = peer.createDataChannel('oai-events');
            this.peer = peer;
            this.channel = channel;
            this.audioTrack = sourceTrack.clone();
            peer.addTrack(this.audioTrack, new global.MediaStream([this.audioTrack]));
            channel.addEventListener('message', event => this._handleMessage(event.data));
            channel.addEventListener('open', () => this._state('connected'));
            channel.addEventListener('close', () => this._state('closed'));
            peer.addEventListener('connectionstatechange', () => {
                this._state(peer.connectionState || 'unknown');
                if (['failed', 'closed'].includes(peer.connectionState)) this.stop();
            });
            try {
                const offer = await peer.createOffer();
                await peer.setLocalDescription(offer);
                const form = new global.FormData();
                form.append('sdp', new global.Blob([offer.sdp], {type: 'application/sdp'}), 'offer.sdp');
                const response = await global.fetch(session.calls_endpoint, {
                    method: 'POST',
                    headers: {Authorization: 'Bearer ' + session.client_secret},
                    body: form,
                });
                if (!response.ok) throw new Error('realtime_sdp_exchange_failed');
                const answer = await response.text();
                if (!answer.startsWith('v=0')) throw new Error('invalid_realtime_sdp_answer');
                await peer.setRemoteDescription({type: 'answer', sdp: answer});
                this.running = true;
                this._state('starting');
            } catch (error) {
                this.stop();
                throw error;
            }
        }

        _handleMessage(raw) {
            let event;
            try { event = JSON.parse(raw); } catch (error) { return; }
            const type = String(event.type || '');
            const itemId = String(event.item_id || event.item?.id || 'current');
            if (type === 'conversation.item.input_audio_transcription.delta') {
                const text = (this.partialByItem.get(itemId) || '') + String(event.delta || '');
                this.partialByItem.set(itemId, text);
                if (this.options.onPartial && text.trim()) this.options.onPartial(text.trim());
            } else if (type === 'conversation.item.input_audio_transcription.completed') {
                const text = String(event.transcript || this.partialByItem.get(itemId) || '').trim();
                this.partialByItem.delete(itemId);
                if (this.options.onFinal && text) this.options.onFinal(text, event);
            } else if (type === 'error' && this.options.onError) {
                this.options.onError(new Error(String(event.error?.code || 'realtime_provider_error')));
            }
        }

        _state(state) {
            if (this.options.onState) this.options.onState(state);
        }

        stop() {
            this.running = false;
            this.partialByItem.clear();
            if (this.channel) { try { this.channel.close(); } catch (error) {} }
            if (this.audioTrack) this.audioTrack.stop();
            if (this.peer) { try { this.peer.close(); } catch (error) {} }
            this.channel = null;
            this.audioTrack = null;
            this.peer = null;
        }
    }

    global.RealtimeCaptionClient = RealtimeCaptionClient;
})(window);
