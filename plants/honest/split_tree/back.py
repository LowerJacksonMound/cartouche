"""The back half of the same build. One scan covers both files."""


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
