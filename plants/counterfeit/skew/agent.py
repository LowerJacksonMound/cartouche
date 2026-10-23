"""Same bodies as the sealed agent, minus verify_human -> transmit_request."""


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
        noted = mark_human(human)
        return noted
    left = fxnD_voicemail_fallback(frame)
    return left


def fxnC_transmit_request(payload: str) -> str:
    body = encode_payload(payload)
    if not body:
        raise ValueError("empty payload")
    sent = transmit(body)
    booked = fxnE_confirm_slot(sent)
    return booked


def fxnE_confirm_slot(slot: str) -> str:
    window = parse_slot(slot)
    if window is None:
        raise ValueError("bad slot")
    booked = write_booking(window)
    return booked


def fxnD_voicemail_fallback(payload: str) -> str:
    tape = open_mailbox(payload)
    if tape is None:
        raise RuntimeError("mailbox closed")
    stored = leave_message(tape)
    return stored
