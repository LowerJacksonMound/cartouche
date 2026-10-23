"""The request domain. The stitcher, not a hand list, certifies the track."""

from __future__ import annotations

import json
from pathlib import Path

DOMAIN_ID = "automotive_phone_appointment_v1"
INTERACTION = "phone_conversation"
EXAMPLE_DIR = Path(__file__).resolve().parent / "tests" / "fixture"

# Slot anatomy is intentional. Alphabetical order would swap the tear duct and the lower lid.
SLOTS: dict[str, int] = {
    "fxnA_dial": 0,
    "fxnB_verify_human": 1,
    "fxnC_transmit_request": 2,
    "fxnE_confirm_slot": 3,
    "fxnD_voicemail_fallback": 4,
}

PHRASES: dict[str, tuple[str, str]] = {
    "fxnA_dial": ("tok_dial", "Dick's Automotive, how can I help you?"),
    "fxnB_verify_human": ("tok_human", "Yeah, this is Mike."),
    "fxnC_transmit_request": (
        "tok_payload",
        "I need to book a Tuesday morning slot for a 1989 Lotus Esprit.",
    ),
    "fxnE_confirm_slot": ("tok_confirm", "You're on the books for Tuesday at 9."),
    "fxnD_voicemail_fallback": ("tok_vm", "Please leave a message after the tone."),
}

REQUEST: dict[str, str] = {
    "shop": "Dick's Automotive",
    "caller": "Mike",
    "vehicle": "1989 Lotus Esprit",
    "window": "Tuesday morning",
}

PARAMS: dict[str, list[str]] = {
    "fxnA_dial": ["shop_number"],
    "fxnB_verify_human": ["audio_frame"],
    "fxnC_transmit_request": ["payload"],
    "fxnE_confirm_slot": ["slot"],
    "fxnD_voicemail_fallback": ["payload"],
}

EDGES: list[list[str]] = [
    ["fxnA_dial", "fxnB_verify_human"],
    ["fxnB_verify_human", "fxnC_transmit_request"],
    ["fxnC_transmit_request", "fxnE_confirm_slot"],
    ["fxnB_verify_human", "fxnD_voicemail_fallback"],
]

FIXTURES: list[tuple[str, str, str]] = [
    (
        "sealed",
        "Sealed",
        "Direct calls cover every required edge. Residual must be 0.",
    ),
    (
        "hazy",
        "Hazy cornea",
        "verify_human returns True. The cornea should blur, not drop out.",
    ),
    (
        "shifted",
        "Shifted caller",
        "The verify-to-transmit edge is gone. That piece of the Eye skews.",
    ),
    (
        "esprit",
        "Esprit",
        "Voicemail is missing and confirm is a pass stub. The Eye is not whole.",
    ),
]


def invariants() -> dict[str, dict]:
    return {
        name: {
            "min_ast_nodes": 4,
            "forbid_bare_except": True,
            "forbid_constant_return": True,
        }
        for name in SLOTS
    }


def domain_spec() -> dict:
    b_roll = {
        token: {"phrase": phrase, "clip_path": f"clips/{token}.mp4"}
        for _name, (token, phrase) in PHRASES.items()
    }
    nodes: dict[str, dict] = {}
    happy = [
        "fxnA_dial",
        "fxnB_verify_human",
        "fxnC_transmit_request",
        "fxnE_confirm_slot",
    ]
    root = None
    previous = None
    for index, name in enumerate(happy):
        node_id = f"n{index}"
        token, _phrase = PHRASES[name]
        nodes[node_id] = {
            "token_id": token,
            "primitive_fxn": name,
            "glyph_slot": SLOTS[name],
            "is_edge_case": False,
            "branches": [],
        }
        if previous is None:
            root = node_id
        else:
            nodes[previous]["branches"].append({"target_node": node_id})
        previous = node_id
    token, _phrase = PHRASES["fxnD_voicemail_fallback"]
    nodes["n_vm"] = {
        "token_id": token,
        "primitive_fxn": "fxnD_voicemail_fallback",
        "glyph_slot": SLOTS["fxnD_voicemail_fallback"],
        "is_edge_case": True,
        "branches": [],
    }
    nodes["n1"]["branches"].append({"target_node": "n_vm"})
    return {
        "domain_id": DOMAIN_ID,
        "interaction": INTERACTION,
        "cartouche_capacity": 3,
        "root_id": root,
        "b_roll_atoms": b_roll,
        "nodes": nodes,
        "primitive_params": PARAMS,
        "primitive_invariants": invariants(),
        "parameters": dict(REQUEST),
    }


def signal_track() -> dict:
    from cartouche.signal_stitcher import SignalStitcher

    return SignalStitcher(domain_spec(), base_dir=EXAMPLE_DIR).compile_montage_and_signals()


def fixture_path(fixture_id: str) -> Path:
    return {
        "sealed": EXAMPLE_DIR / "agent_sealed.py",
        "hazy": EXAMPLE_DIR / "agent_hazy_verify.py",
        "shifted": EXAMPLE_DIR / "agent_shifted_edge.py",
        "esprit": EXAMPLE_DIR / "agent_esprit.py",
    }[fixture_id]


def write_checked_in_json() -> None:
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    (EXAMPLE_DIR / "certified_signal_track.json").write_text(
        json.dumps(signal_track(), indent=2) + "\n", encoding="utf-8"
    )
    (EXAMPLE_DIR / "domain_spec.json").write_text(
        json.dumps(domain_spec(), indent=2) + "\n", encoding="utf-8"
    )
