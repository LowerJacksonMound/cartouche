"""Phase-1 gate: slots, fidelity, the four phone fixtures, hash stability."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.cartouche_scanner import ASTTopologyExtractor, CartoucheScanner
from cartouche.cli import main
from cartouche.domain import (
    EXAMPLE_DIR,
    SLOTS,
    fixture_path,
    signal_track,
    write_checked_in_json,
)

NS = {"svg": "http://www.w3.org/2000/svg"}


def _compile() -> dict:
    return CartoucheCompiler(signal_track()).compile_cartouche()


def _scan(fixture_id: str, master: dict | None = None) -> tuple[dict, str]:
    master = master or _compile()
    report = CartoucheScanner(master).scan_file(fixture_path(fixture_id))
    svg = CartoucheCompiler.render_svg(
        master, report["glyph_diagnostics"], report["broken_edges"]
    )
    return report, svg


def _titles(svg: str) -> dict[str, ET.Element]:
    root = ET.fromstring(svg)
    found: dict[str, ET.Element] = {}
    for poly in root.findall("svg:polygon", NS):
        title = poly.find("svg:title", NS)
        if title is not None and title.text:
            name = title.text.split(" | ", 1)[0]
            found[name] = poly
    return found


class CompileTests(unittest.TestCase):
    def test_slots_match_anatomy_not_alpha_sort(self) -> None:
        master = _compile()
        glyphs = master["sub_glyphs"]
        self.assertEqual(glyphs["fxnB_verify_human"]["sign_name"], "the mouth")
        self.assertEqual(glyphs["fxnD_voicemail_fallback"]["sign_name"], "the cloth")
        self.assertEqual(glyphs["fxnE_confirm_slot"]["sign_name"], "the house")
        ids = {glyph["sign_id"] for glyph in glyphs.values()}
        self.assertEqual(len(ids), len(glyphs))
        self.assertNotIn("region_name", glyphs["fxnA_dial"])
        self.assertNotIn("svg_polygon", glyphs["fxnA_dial"])
        self.assertEqual(glyphs["fxnD_voicemail_fallback"]["bit_mask"], 1 << 4)
        self.assertEqual(glyphs["fxnE_confirm_slot"]["bit_mask"], 1 << 3)
        self.assertEqual(master["expected_full_bitmask"], 31)
        self.assertEqual(
            [name for name, _slot in sorted(SLOTS.items(), key=lambda item: item[1])],
            list(glyphs),
        )

    def test_hash_stable_across_calls(self) -> None:
        first = _compile()["cartouche_sha256"]
        second = _compile()["cartouche_sha256"]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_duplicate_slot_rejected(self) -> None:
        track = signal_track()
        track["glyph_slots"] = dict(track["glyph_slots"])
        track["glyph_slots"]["fxnE_confirm_slot"] = 4
        with self.assertRaises(ValueError):
            CartoucheCompiler(track).compile_cartouche()

    def test_checked_in_track_matches_builder(self) -> None:
        write_checked_in_json()
        on_disk = json.loads(
            (EXAMPLE_DIR / "certified_signal_track.json").read_text(encoding="utf-8")
        )
        self.assertEqual(on_disk, signal_track())


class FixtureTests(unittest.TestCase):
    def test_sealed(self) -> None:
        report, svg = _scan("sealed")
        self.assertTrue(report["is_sealed"])
        self.assertEqual(report["projection_residual"], 0.0)
        self.assertEqual(report["active_bitmask"], 31)
        self.assertEqual(report["missing_bitmask_delta"], 0)
        self.assertEqual(report["broken_edges"], [])
        self.assertEqual(report["warrant_count"], 0)
        self.assertIn('color="#10b981"', svg)
        self.assertIn("Projection Residual: 0.00 | Edge Faults: 0", svg)
        self.assertNotIn("skewX", svg)

    def test_hazy_cornea(self) -> None:
        report, svg = _scan("hazy")
        diag = report["glyph_diagnostics"]["fxnB_verify_human"]
        self.assertEqual(diag["fidelity"], 0.30)
        self.assertEqual(
            diag["faults"],
            ["DEGENERATE_CONSTANT_RETURN", "LOW_AST_DENSITY(0<4)"],
        )
        self.assertEqual(report["projection_residual"], 0.70)
        self.assertFalse(report["is_sealed"])
        self.assertEqual(report["active_bitmask"], 29)
        self.assertEqual(report["missing_bitmask_delta"], 2)
        self.assertEqual(report["broken_edges"], [])
        self.assertEqual(report["warrant_count"], 1)
        warrant = report["closer_warrants"][0]
        self.assertEqual(warrant["warrant_type"], "CARTOUCHE_MALFORMED_GLYPH")
        self.assertEqual(warrant["cartouche_region"], "the mouth")
        self.assertEqual(warrant["glyph_fidelity"], 0.30)
        self.assertIn('stdDeviation="3.15"', svg)
        self.assertIn("fxnB_verify_human", svg)
        self.assertIn("Projection Residual: 0.70", svg)
        self.assertIn('fill="#f59e0b"', svg.split("<text", 1)[1])

    def test_return_true_is_not_a_stub(self) -> None:
        source = fixture_path("hazy").read_text(encoding="utf-8")
        tree = ast.parse(source)
        extractor = ASTTopologyExtractor()
        extractor.visit(tree)
        info = extractor.defined_functions["fxnB_verify_human"]
        self.assertFalse(info["is_stub"])
        self.assertTrue(info["only_constant_returns"])
        self.assertEqual(info["ast_density"], 0)

    def test_shifted_caller(self) -> None:
        report, svg = _scan("shifted")
        self.assertEqual(
            report["broken_edges"],
            [["fxnB_verify_human", "fxnC_transmit_request"]],
        )
        self.assertEqual(report["projection_residual"], 1.0)
        self.assertEqual(report["active_bitmask"], 31)
        self.assertFalse(report["is_sealed"])
        self.assertEqual(report["warrant_count"], 1)
        self.assertEqual(
            report["closer_warrants"][0]["warrant_type"], "CARTOUCHE_TOPOLOGY_BREAK"
        )
        self.assertEqual(svg.count("skewX"), 1)
        self.assertIn('fill="#f59e0b"', svg.split("<text", 1)[1])

    def test_esprit(self) -> None:
        report, svg = _scan("esprit")
        self.assertEqual(report["active_bitmask"], 7)
        self.assertEqual(report["expected_bitmask"], 31)
        self.assertEqual(report["missing_bitmask_delta"], 24)
        self.assertEqual(report["projection_residual"], 4.0)
        self.assertFalse(report["is_sealed"])
        self.assertEqual(
            report["broken_edges"],
            [
                ["fxnB_verify_human", "fxnD_voicemail_fallback"],
                ["fxnC_transmit_request", "fxnE_confirm_slot"],
            ],
        )
        types = [w["warrant_type"] for w in report["closer_warrants"]]
        self.assertEqual(
            types,
            [
                "CARTOUCHE_COUNTERFEIT_STUB",
                "CARTOUCHE_MISSING_GLYPH",
                "CARTOUCHE_TOPOLOGY_BREAK",
                "CARTOUCHE_TOPOLOGY_BREAK",
            ],
        )
        by_type = {w["warrant_type"]: w for w in report["closer_warrants"]}
        self.assertEqual(by_type["CARTOUCHE_MISSING_GLYPH"]["missing_primitive"], "fxnD_voicemail_fallback")
        self.assertEqual(by_type["CARTOUCHE_MISSING_GLYPH"]["cartouche_region"], "the cloth")
        self.assertEqual(by_type["CARTOUCHE_MISSING_GLYPH"]["line_range"], [1, 1])
        stub = by_type["CARTOUCHE_COUNTERFEIT_STUB"]
        self.assertEqual(stub["missing_primitive"], "fxnE_confirm_slot")
        self.assertEqual(stub["cartouche_region"], "the house")
        self.assertGreater(stub["line_range"][0], 1)
        self.assertEqual(report["glyph_diagnostics"]["fxnD_voicemail_fallback"]["fidelity"], 0.0)
        self.assertEqual(report["glyph_diagnostics"]["fxnE_confirm_slot"]["faults"], ["HOLLOW_STUB"])
        self.assertIn('color="#ef4444"', svg)
        self.assertIn('stroke-dasharray="4 3"', svg)
        self.assertIn('fill="#ef4444"', svg.split("<text", 1)[1])

    def test_svg_is_well_formed(self) -> None:
        for fixture_id in ("sealed", "hazy", "shifted", "esprit"):
            _svg = _scan(fixture_id)[1]
            ET.fromstring(_svg)


class RuleTests(unittest.TestCase):
    def test_thin_wrapper_respects_min_ast_nodes(self) -> None:
        track = {
            "domain_id": "thin",
            "required_primitives": {"fxn_wrap": "abc"},
            "required_edges": [],
            "glyph_slots": {"fxn_wrap": 0},
            "primitive_params": {"fxn_wrap": ["sock"]},
            "primitive_invariants": {
                "fxn_wrap": {
                    "min_ast_nodes": 1,
                    "forbid_bare_except": True,
                    "forbid_constant_return": True,
                }
            },
        }
        master = CartoucheCompiler(track).compile_cartouche()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wrap.py"
            path.write_text(
                "def fxn_wrap(sock):\n    return open_sock(sock)\n", encoding="utf-8"
            )
            report = CartoucheScanner(master).scan_file(path)
        self.assertTrue(report["is_sealed"])
        self.assertEqual(report["glyph_diagnostics"]["fxn_wrap"]["fidelity"], 1.0)

    def test_orchestrator_satisfies_edge(self) -> None:
        body = (
            "def fxn_a(x):\n"
            "    y = step(x)\n"
            "    if y is None:\n"
            "        raise RuntimeError('no')\n"
            "    z = step(y)\n"
            "    return z\n"
            "def fxn_b(x):\n"
            "    y = step(x)\n"
            "    if y is None:\n"
            "        raise RuntimeError('no')\n"
            "    z = step(y)\n"
            "    return z\n"
            "def orch(x):\n"
            "    fxn_a(x)\n"
            "    fxn_b(x)\n"
        )
        track = {
            "domain_id": "orch",
            "required_primitives": {"fxn_a": "a", "fxn_b": "b"},
            "required_edges": [["fxn_a", "fxn_b"]],
            "glyph_slots": {"fxn_a": 0, "fxn_b": 1},
            "primitive_params": {"fxn_a": ["x"], "fxn_b": ["x"]},
            "primitive_invariants": {},
        }
        master = CartoucheCompiler(track).compile_cartouche()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orch.py"
            path.write_text(body, encoding="utf-8")
            report = CartoucheScanner(master).scan_file(path)
        self.assertTrue(report["is_sealed"], report)
        self.assertEqual(report["broken_edges"], [])

    def test_missing_params_bare_except_and_floor(self) -> None:
        track = signal_track()
        master = CartoucheCompiler(track).compile_cartouche()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.py"
            path.write_text(
                "def fxnA_dial(shop_number):\n"
                "    y = step(shop_number)\n"
                "    if y is None:\n"
                "        raise RuntimeError('no')\n"
                "    z = step(y)\n"
                "    return z\n"
                "def fxnB_verify_human():\n"
                "    try:\n"
                "        return True\n"
                "    except:\n"
                "        return False\n"
                "def fxnC_transmit_request(payload):\n"
                "    y = step(payload)\n"
                "    if y is None:\n"
                "        raise RuntimeError('no')\n"
                "    z = step(y)\n"
                "    return z\n"
                "def fxnE_confirm_slot(slot):\n"
                "    y = step(slot)\n"
                "    if y is None:\n"
                "        raise RuntimeError('no')\n"
                "    z = step(y)\n"
                "    return z\n"
                "def fxnD_voicemail_fallback(payload):\n"
                "    y = step(payload)\n"
                "    if y is None:\n"
                "        raise RuntimeError('no')\n"
                "    z = step(y)\n"
                "    return z\n"
                "def orch(shop_number, audio_frame, payload, slot):\n"
                "    fxnA_dial(shop_number)\n"
                "    fxnB_verify_human()\n"
                "    fxnC_transmit_request(payload)\n"
                "    fxnE_confirm_slot(slot)\n"
                "    fxnD_voicemail_fallback(payload)\n",
                encoding="utf-8",
            )
            report = CartoucheScanner(master).scan_file(path)
        diag = report["glyph_diagnostics"]["fxnB_verify_human"]
        self.assertEqual(diag["fidelity"], 0.10)
        self.assertIn("MISSING_PARAMS(audio_frame)", diag["faults"])
        self.assertIn("DEGENERATE_CONSTANT_RETURN", diag["faults"])
        self.assertIn("SWALLOWED_BARE_EXCEPT", diag["faults"])
        self.assertTrue(any(f.startswith("LOW_AST_DENSITY") for f in diag["faults"]))

    def test_jeopardy_hash_is_stable_and_fault_sensitive(self) -> None:
        report, _svg = _scan("hazy")
        again, _svg2 = _scan("hazy")
        first = report["closer_warrants"][0]["double_jeopardy_hash"]
        self.assertEqual(first, again["closer_warrants"][0]["double_jeopardy_hash"])
        self.assertEqual(len(first), 20)
        expected = hashlib.sha256(
            b"agent_hazy_verify.py::MALFORMED::DEGENERATE_CONSTANT_RETURN,LOW_AST_DENSITY(0<4)::fxnB_verify_human"
        ).hexdigest()[:20]
        self.assertEqual(first, expected)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent_hazy_verify.py"
            path.write_text(
                "def fxnA_dial(shop_number):\n"
                "    y = step(shop_number)\n"
                "    if y is None:\n"
                "        raise RuntimeError('no')\n"
                "    z = step(y)\n"
                "    return z\n"
                "def fxnB_verify_human(audio_frame):\n"
                "    try:\n"
                "        return True\n"
                "    except:\n"
                "        return True\n"
                "def fxnC_transmit_request(payload):\n"
                "    y = step(payload)\n"
                "    if y is None:\n"
                "        raise RuntimeError('no')\n"
                "    z = step(y)\n"
                "    return z\n"
                "def fxnE_confirm_slot(slot):\n"
                "    y = step(slot)\n"
                "    if y is None:\n"
                "        raise RuntimeError('no')\n"
                "    z = step(y)\n"
                "    return z\n"
                "def fxnD_voicemail_fallback(payload):\n"
                "    y = step(payload)\n"
                "    if y is None:\n"
                "        raise RuntimeError('no')\n"
                "    z = step(y)\n"
                "    return z\n"
                "def run(a, b, c, d):\n"
                "    fxnA_dial(a)\n"
                "    fxnB_verify_human(b)\n"
                "    fxnC_transmit_request(c)\n"
                "    fxnE_confirm_slot(d)\n"
                "    fxnD_voicemail_fallback(c)\n",
                encoding="utf-8",
            )
            changed = CartoucheScanner(_compile()).scan_file(path)
        new_hash = changed["closer_warrants"][0]["double_jeopardy_hash"]
        self.assertNotEqual(new_hash, first)
        self.assertIn("SWALLOWED_BARE_EXCEPT", changed["closer_warrants"][0]["faults"])


class CliTests(unittest.TestCase):
    def test_gate_exit_codes(self) -> None:
        write_checked_in_json()
        track = EXAMPLE_DIR / "certified_signal_track.json"
        with tempfile.TemporaryDirectory() as tmp:
            sealed_out = Path(tmp) / "sealed"
            code = main(["gate", str(track), str(fixture_path("sealed")), "-o", str(sealed_out)])
            self.assertEqual(code, 0)
            self.assertTrue((sealed_out / "cartouche.svg").is_file())
            report = json.loads((sealed_out / "scan_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["is_sealed"])

            esprit_out = Path(tmp) / "esprit"
            code = main(["gate", str(track), str(fixture_path("esprit")), "-o", str(esprit_out)])
            self.assertEqual(code, 2)
            self.assertIn("fxnD_voicemail_fallback", (esprit_out / "cartouche.svg").read_text(encoding="utf-8"))
            self.assertIn("MISSING_FUNCTION", (esprit_out / "cartouche.svg").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
