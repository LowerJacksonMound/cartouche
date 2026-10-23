"""A request matches the certified phrases or it does not. The lock does not move."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cartouche.cli import main
from cartouche.instantiate import instantiate
from cartouche.domain import REQUEST, domain_spec
from cartouche.tests.test_stitcher import PHASE1_SHA


class InstantiateTests(unittest.TestCase):
    def test_the_certified_request_holds_the_phone_lock(self) -> None:
        result = instantiate(domain_spec(), dict(REQUEST))
        self.assertTrue(result["held"])
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(result["unknown"], [])
        self.assertEqual(result["parameters"], REQUEST)
        self.assertEqual(result["cartouche_sha256"], PHASE1_SHA)

    def test_a_different_vehicle_is_not_a_new_cartouche(self) -> None:
        request = dict(REQUEST)
        request["vehicle"] = "1990 Lotus Esprit"
        result = instantiate(domain_spec(), request)
        self.assertFalse(result["held"])
        self.assertEqual(result["mismatches"], ["vehicle"])
        self.assertEqual(result["parameters"]["vehicle"], "1989 Lotus Esprit")
        self.assertEqual(result["cartouche_sha256"], PHASE1_SHA)

    def test_an_unknown_field_is_not_held(self) -> None:
        request = dict(REQUEST)
        request["color"] = "red"
        result = instantiate(domain_spec(), request)
        self.assertFalse(result["held"])
        self.assertEqual(result["unknown"], ["color"])

    def test_a_parameter_missing_from_the_phrases_is_refused(self) -> None:
        spec = domain_spec()
        spec["parameters"] = dict(REQUEST)
        spec["parameters"]["shop"] = "Some Other Shop"
        with self.assertRaises(ValueError):
            instantiate(spec, dict(REQUEST))

    def test_cli_does_not_rewrite_the_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "domain_spec.json"
            spec.write_text(json.dumps(domain_spec()), encoding="utf-8")
            before = spec.read_text(encoding="utf-8")
            request = root / "request.json"
            request.write_text(json.dumps(REQUEST), encoding="utf-8")
            out = root / "binding.json"
            self.assertEqual(main(["instantiate", str(spec), str(request), "-o", str(out)]), 0)
            self.assertEqual(spec.read_text(encoding="utf-8"), before)
            body = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(body["held"])
            self.assertEqual(body["cartouche_sha256"], PHASE1_SHA)
            request.write_text(
                json.dumps({**REQUEST, "window": "Wednesday"}),
                encoding="utf-8",
            )
            self.assertEqual(main(["instantiate", str(spec), str(request), "-o", str(out)]), 2)
            self.assertEqual(spec.read_text(encoding="utf-8"), before)
            missed = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(missed["mismatches"], ["window"])
            self.assertEqual(missed["cartouche_sha256"], PHASE1_SHA)


if __name__ == "__main__":
    unittest.main()
