"""Every name and signature from the request, and nothing behind any of them. A template is not a build."""


def fxnA_dial(shop_number: str) -> str:
    """Dial the shop."""


def fxnB_verify_human(audio_frame: bytes) -> str:
    """Check that a person answered."""
    ...


def fxnC_transmit_request(payload: str) -> str:
    """Send the booking request."""
    pass


def fxnE_confirm_slot(slot: str) -> str:
    """Confirm the slot."""


def fxnD_voicemail_fallback(payload: str) -> str:
    """Leave a message."""
    pass
