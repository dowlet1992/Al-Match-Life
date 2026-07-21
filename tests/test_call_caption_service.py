from backend.services import call_caption_service


def test_caption_segments_are_bounded_and_only_return_remote_updates():
    room = {"captions": []}
    for index in range(125):
        call_caption_service.append_segment(room, {
            "id": str(index),
            "speaker_email": "alice@example.com" if index % 2 else "bob@example.com",
            "text": f"segment {index}",
            "created_at": 100 + index,
        }, now=225)

    assert len(room["captions"]) == call_caption_service.MAX_ROOM_CAPTIONS
    remote = call_caption_service.segments_after(room, after=220, exclude_email="alice@example.com", now=225)
    assert all(item["speaker_email"] == "bob@example.com" for item in remote)


def test_caption_text_is_cleaned_and_limited():
    result = call_caption_service.clean_segment("<b>hello</b>" + "x" * 1200, lambda value: str(value).replace("<b>", "").replace("</b>", ""))

    assert result.startswith("hello")
    assert len(result) == call_caption_service.MAX_CAPTION_LENGTH


def test_closed_call_purges_all_temporary_caption_data():
    room = {
        "status": "ended",
        "captions": [{"id": "caption"}],
        "transcription_reservations": [{"sequence": 1}],
        "quality_samples": [{"rtt_ms": 20}],
        "messages": [{"type": "ended"}],
    }

    assert call_caption_service.purge_temporary_data(room) is True
    assert "captions" not in room
    assert "transcription_reservations" not in room
    assert "quality_samples" not in room
    assert room["messages"] == [{"type": "ended"}]
    assert call_caption_service.purge_temporary_data(room) is False
