"""Sealed phone-appointment agent. Every required call edge is direct."""


def fxnA_dial(shop_number: str) -> str:
    channel = open_line(shop_number)
    if channel is None:
        raise ConnectionError("dial failed")
    armed = arm_channel(channel)
    fxnB_verify_human(armed)
    return armed


def fxnB_verify_human(audio_frame: bytes) -> str:
    frame = normalize_frame(audio_frame)
    if frame is None:
        raise ValueError("empty frame")
    human = detect_voice(frame)
    if human:
        sent = fxnC_transmit_request(human)
        return sent
    left = fxnD_voicemail_fallback(frame)
    return left


