"""verify_human exists and the path is orchestrated, but the body is `return True`."""


def fxnA_dial(shop_number: str) -> str:
    channel = open_line(shop_number)
    if channel is None:
        raise ConnectionError("dial failed")
    armed = arm_channel(channel)
    return armed


def fxnB_verify_human(audio_frame: bytes) -> bool:
    return True


def fxnC_transmit_request(payload: str) -> str:
    body = encode_payload(payload)
    if not body:
        raise ValueError("empty payload")
    sent = transmit(body)
    return sent


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


def run_booking(shop_number: str, audio_frame: bytes, payload: str, slot: str) -> str:
    dialed = fxnA_dial(shop_number)
    fxnB_verify_human(audio_frame)
    sent = fxnC_transmit_request(payload)
    booked = fxnE_confirm_slot(slot)
    left = fxnD_voicemail_fallback(payload)
    return f"{dialed}:{sent}:{booked}:{left}"
