import math


MAX_QUALITY_SAMPLES = 24
QUALITY_LEVELS = {"good", "fair", "poor"}


def bounded_number(value, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    if not math.isfinite(number):
        number = minimum
    return round(min(max(number, minimum), maximum), 2)


def classify_quality(rtt_ms, jitter_ms, packet_loss_percent):
    if packet_loss_percent >= 8 or rtt_ms >= 800 or jitter_ms >= 80:
        return "poor"
    if packet_loss_percent >= 3 or rtt_ms >= 350 or jitter_ms >= 35:
        return "fair"
    return "good"


def normalize_sample(data, participant_email, created_at):
    rtt_ms = bounded_number(data.get("rtt_ms"), 0, 60_000)
    jitter_ms = bounded_number(data.get("jitter_ms"), 0, 10_000)
    packet_loss = bounded_number(data.get("packet_loss_percent"), 0, 100)
    bitrate = bounded_number(data.get("bitrate_kbps"), 0, 1_000_000)
    return {
        "participant_email": str(participant_email or "").strip().lower(),
        "rtt_ms": rtt_ms,
        "jitter_ms": jitter_ms,
        "packet_loss_percent": packet_loss,
        "bitrate_kbps": bitrate,
        "quality": classify_quality(rtt_ms, jitter_ms, packet_loss),
        "relay": data.get("relay") is True,
        "created_at": float(created_at),
    }


def percentile(values, percent):
    values = sorted(float(value) for value in values)
    if not values:
        return 0
    index = max(min(math.ceil((percent / 100) * len(values)) - 1, len(values) - 1), 0)
    return round(values[index], 2)


def summarize_samples(samples):
    samples = [sample for sample in samples if isinstance(sample, dict)]
    metrics = {name: [] for name in ("rtt_ms", "jitter_ms", "packet_loss_percent", "bitrate_kbps")}
    quality_counts = {level: 0 for level in sorted(QUALITY_LEVELS)}
    relay_count = 0
    for sample in samples:
        for name in metrics:
            metrics[name].append(bounded_number(sample.get(name), 0, 1_000_000))
        quality = sample.get("quality")
        if quality in quality_counts:
            quality_counts[quality] += 1
        relay_count += int(sample.get("relay") is True)
    return {
        "sample_count": len(samples),
        "quality_counts": quality_counts,
        "relay_count": relay_count,
        "metrics": {
            name: {"p50": percentile(values, 50), "p95": percentile(values, 95)}
            for name, values in metrics.items()
        },
    }


def aggregate_rooms(rooms):
    rooms = [room for room in rooms.values() if isinstance(room, dict)] if isinstance(rooms, dict) else []
    terminal = {"ended", "declined", "missed"}
    summaries = []
    successful = 0
    relay_rooms = 0
    reasons = {}
    status_counts = {}
    for room in rooms:
        status = str(room.get("status", "active"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if room.get("accepted_at"):
            successful += 1
        summary = room.get("quality_summary")
        if not isinstance(summary, dict):
            summary = summarize_samples(room.get("quality_samples", []))
        if summary.get("sample_count", 0):
            summaries.append(summary)
            relay_rooms += int(summary.get("relay_count", 0) > 0)
        if status in terminal:
            reason = "completed" if status == "ended" else status
            messages = room.get("messages", []) if isinstance(room.get("messages", []), list) else []
            for message in reversed(messages):
                if isinstance(message, dict) and message.get("type") in terminal:
                    payload = message.get("payload", {}) if isinstance(message.get("payload"), dict) else {}
                    requested_reason = str(payload.get("reason", ""))
                    reason = requested_reason if requested_reason in {"connection_lost", "negotiation_timeout"} else ("completed" if status == "ended" else status)
                    break
            reasons[reason] = reasons.get(reason, 0) + 1
    metric_summary = {}
    quality_counts = {level: 0 for level in sorted(QUALITY_LEVELS)}
    total_samples = 0
    for summary in summaries:
        total_samples += int(summary.get("sample_count", 0) or 0)
        for level in quality_counts:
            quality_counts[level] += int(summary.get("quality_counts", {}).get(level, 0) or 0)
    for name in ("rtt_ms", "jitter_ms", "packet_loss_percent", "bitrate_kbps"):
        p50_values = [item.get("metrics", {}).get(name, {}).get("p50", 0) for item in summaries]
        p95_values = [item.get("metrics", {}).get(name, {}).get("p95", 0) for item in summaries]
        metric_summary[name] = {"p50": percentile(p50_values, 50), "p95": percentile(p95_values, 95)}
    total = len(rooms)
    return {
        "room_count": total,
        "successful_room_count": successful,
        "connection_success_rate": round((successful / total) * 100, 2) if total else 0,
        "rooms_with_quality_data": len(summaries),
        "quality_sample_count": total_samples,
        "quality_counts": quality_counts,
        "turn_room_rate": round((relay_rooms / len(summaries)) * 100, 2) if summaries else 0,
        "status_counts": status_counts,
        "end_reasons": reasons,
        "metrics": metric_summary,
    }
