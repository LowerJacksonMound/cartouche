"""Dials, speaks, hangs up. Voicemail is absent. Confirm is a hollow pass."""


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
    sent = fxnC_transmit_request(human)
    return sent


def fxnC_transmit_request(payload: str) -> str:
    body = encode_payload(payload)
    if not body:
        raise ValueError("empty payload")
    sent = transmit(body)
    return sent


def fxnE_confirm_slot(slot: str) -> str:
    pass
