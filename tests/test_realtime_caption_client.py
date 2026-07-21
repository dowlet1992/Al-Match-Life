from pathlib import Path


CLIENT_PATH = Path(__file__).resolve().parents[1] / "static" / "realtime-caption-client.js"


def test_realtime_caption_client_uses_ephemeral_secret_and_multipart_sdp():
    source = CLIENT_PATH.read_text(encoding="utf-8")
    assert "Authorization: 'Bearer ' + session.client_secret" in source
    assert "application/sdp" in source
    assert "session.calls_endpoint" in source
    assert "OPENAI_API_KEY" not in source


def test_realtime_caption_client_handles_deltas_final_events_and_cleanup():
    source = CLIENT_PATH.read_text(encoding="utf-8")
    assert "conversation.item.input_audio_transcription.delta" in source
    assert "conversation.item.input_audio_transcription.completed" in source
    assert "this.audioTrack = sourceTrack.clone()" in source
    assert "this.audioTrack.stop()" in source
    assert "this.peer.close()" in source
