from backend.repositories.call_signal_repository import get_call_signal_repository


def load_call_signals():
    return get_call_signal_repository().load_all()


def save_call_signals(data):
    get_call_signal_repository().save_all(data)


def get_call_signal_room(room_id):
    return get_call_signal_repository().get_room(room_id)


def append_call_signal(room_id, signal, **options):
    return get_call_signal_repository().append_signal(room_id, signal, **options)


def delete_call_rooms_for_participant(email):
    return get_call_signal_repository().delete_for_participant(email)


def prune_expired_call_rooms(**options):
    return get_call_signal_repository().prune_expired(**options)


def append_call_caption(room_id, segment, max_items=120, minimum_created_at=0):
    return get_call_signal_repository().append_caption(
        room_id, segment, max_items=max_items, minimum_created_at=minimum_created_at,
    )


def append_call_quality_sample(room_id, sample, max_items=24, minimum_interval=4):
    return get_call_signal_repository().append_quality_sample(
        room_id, sample, max_items=max_items, minimum_interval=minimum_interval,
    )


def acknowledge_call_signals(room_id, receiver_email, event_ids, acknowledged_at):
    return get_call_signal_repository().acknowledge_signals(
        room_id, receiver_email, event_ids, acknowledged_at,
    )


def expire_call_signal_room(room_id, now, **options):
    return get_call_signal_repository().expire_room(room_id, now, **options)


def expire_due_call_rooms(now, **options):
    return get_call_signal_repository().expire_due_rooms(now, **options)


def set_call_caption_translation(room_id, caption_id, language, translated_text):
    return get_call_signal_repository().set_caption_translation(
        room_id, caption_id, language, translated_text,
    )


def reserve_call_transcription(room_id, speaker_email, sequence, now, **options):
    return get_call_signal_repository().reserve_transcription(
        room_id, speaker_email, sequence, now, **options,
    )


def purge_call_caption_data(room_id):
    return get_call_signal_repository().purge_caption_data(room_id)
