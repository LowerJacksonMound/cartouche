"""Project a Python AST onto a master cartouche and emit CLOSER warrants."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

_EXECUTABLE = (
    ast.Call,
    ast.If,
    ast.For,
    ast.While,
    ast.Assign,
    ast.AnnAssign,
    ast.Raise,
)


class ASTTopologyExtractor(ast.NodeVisitor):
    """Defined functions, stub detection, direct call edges, structural audit."""

    def __init__(self) -> None:
        self.defined_functions: dict[str, dict[str, Any]] = {}
        self.call_edges: set[tuple[str, str]] = set()
        self._current_fxn: str | None = None

    @staticmethod
    def _is_trivial_stub(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """True only for pass, Ellipsis, or a docstring. `return True` is not a stub."""
        meaningful: list[ast.stmt] = []
        for stmt in node.body:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue
            meaningful.append(stmt)
        return len(meaningful) == 0

    @staticmethod
    def _audit_malformations(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> dict[str, Any]:
        sub_nodes = list(ast.walk(node))
        arg_names = [a.arg for a in node.args.args]
        has_bare_except = any(
            isinstance(n, ast.ExceptHandler) and n.type is None for n in sub_nodes
        )
        returns = [n for n in sub_nodes if isinstance(n, ast.Return)]
        # Degenerate means the answer does not depend on the input: one and the same literal from every return, or
        # literals chosen without any test that reads a parameter. A classifier that returns one of several labels
        # after testing its arguments is a real function (owner ruling 2026-11-03, on fxnB_verify_human).
        constant_values = [r.value.value for r in returns if isinstance(r.value, ast.Constant)]
        all_constant = bool(returns) and len(constant_values) == len(returns)
        tests = [n.test for n in sub_nodes if isinstance(n, (ast.If, ast.IfExp, ast.While))]

        def type_check_only(t: ast.expr) -> bool:
            """`isinstance(x, T)` / `type(x) is T`, possibly negated: a check on the kind of input, not its value.
            A hollow body hides behind one (seen 2026-11-03, a counterfeit refuse_repeat)."""
            while isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
                t = t.operand
            if isinstance(t, ast.Call) and isinstance(t.func, ast.Name) and t.func.id == "isinstance":
                return True
            return isinstance(t, ast.Compare) and any(
                isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "type"
                for c in [t.left, *t.comparators]
            )

        tests = [t for t in tests if not type_check_only(t)]
        reads_param = any(
            isinstance(m, ast.Name) and m.id in arg_names for t in tests for m in ast.walk(t)
        ) or any(
            isinstance(m, ast.Name) and m.id in arg_names
            for n in sub_nodes if isinstance(n, ast.Assign) for m in ast.walk(n.value)
        )
        # A raise guarded by a test on a parameter is an outcome too: a line that validates its input and then
        # says its one fixed sentence is a real function (same ruling, on answer_line).
        raises_on_param = reads_param and any(isinstance(n, ast.Raise) for n in sub_nodes)
        only_constant_returns = all_constant and not raises_on_param and (
            len(set(map(repr, constant_values))) <= 1 or not reads_param
        )
        executable_nodes = [n for n in sub_nodes if isinstance(n, _EXECUTABLE)]
        return {
            "arg_names": arg_names,
            "ast_density": len(executable_nodes),
            "has_bare_except": has_bare_except,
            "only_constant_returns": only_constant_returns,
        }

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_fxn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_fxn(node)

    def _process_fxn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        audit = self._audit_malformations(node)
        self.defined_functions[node.name] = {
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", node.lineno),
            "is_stub": self._is_trivial_stub(node),
            **audit,
        }
        prev_fxn = self._current_fxn
        self._current_fxn = node.name
        self.generic_visit(node)
        self._current_fxn = prev_fxn

    def visit_Call(self, node: ast.Call) -> None:
        if self._current_fxn is not None:
            callee_name: str | None = None
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr
            if callee_name:
                self.call_edges.add((self._current_fxn, callee_name))
        self.generic_visit(node)


_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv"}


def python_files(target: Path) -> list[Path]:
    """Every Python file under a build tree. Dot-directories and caches are not the build."""

    found: list[Path] = []
    for path in sorted(target.rglob("*.py")):
        if not path.is_file():
            continue
        parts = path.relative_to(target).parts
        if any(part in _SKIP_DIRS or part.startswith(".") for part in parts):
            continue
        found.append(path)
    return found


class CartoucheScanner:
    """Scores each sub-glyph and writes topological warrants. Does not patch."""

    def __init__(self, master_cartouche: dict[str, Any]) -> None:
        self.cartouche = master_cartouche

    @staticmethod
    def _build_warrant_hash(file_path: str, violation_type: str, target_symbol: str) -> str:
        raw = f"{file_path}::{violation_type}::{target_symbol}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def scan_file(self, target_py_path: Path) -> dict[str, Any]:
        source = target_py_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(target_py_path))
        extractor = ASTTopologyExtractor()
        extractor.visit(tree)
        return self._project(extractor, lambda _name: target_py_path, target_py_path)

    def scan_tree(self, target: Path) -> dict[str, Any]:
        """One scan of a file or a directory. A file that does not parse does not end the scan."""

        if target.is_file():
            try:
                return self.scan_file(target)
            except SyntaxError as exc:
                return self._unparsed_only(target, exc)
        if not target.is_dir():
            return self._waiting(target)
        files = python_files(target)
        if not files:
            return self._waiting(target)
        extractor = ASTTopologyExtractor()
        origins: dict[str, Path] = {}
        failures: list[tuple[Path, SyntaxError]] = []
        parsed = 0
        for path in files:
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
            except SyntaxError as exc:
                failures.append((path, exc))
                continue
            except OSError:
                failures.append((path, SyntaxError("unreadable")))
                continue
            parsed += 1
            before = {name: dict(info) for name, info in extractor.defined_functions.items()}
            extractor.visit(tree)
            for name, info in extractor.defined_functions.items():
                if before.get(name) != info:
                    origins[name] = path
        if parsed == 0:
            report = self._unparsed_only(failures[0][0], failures[0][1])
            for path, exc in failures[1:]:
                self._add_unparsed(report, path, exc)
            return report
        report = self._project(extractor, lambda name: origins.get(name, target), target)
        for path, exc in failures:
            self._add_unparsed(report, path, exc)
        if failures:
            report["is_sealed"] = False
        return report

    def _waiting(self, target: Path) -> dict[str, Any]:
        expected = self.cartouche["expected_full_bitmask"]
        return {
            "domain_id": self.cartouche["domain_id"],
            "cartouche_sha256": self.cartouche["cartouche_sha256"],
            "is_sealed": False,
            "waiting": True,
            "projection_residual": 0.0,
            "active_bitmask": 0,
            "expected_bitmask": expected,
            "missing_bitmask_delta": expected,
            "glyph_diagnostics": {},
            "broken_edges": [],
            "warrant_count": 0,
            "closer_warrants": [],
            "target": str(target),
        }

    def _unparsed_warrant(self, path: Path, exc: SyntaxError) -> dict[str, Any]:
        line = exc.lineno or 1
        message = exc.msg or "does not parse"
        return {
            "warrant_type": "CARTOUCHE_UNPARSED",
            "double_jeopardy_hash": self._build_warrant_hash(path.name, "UNPARSED", str(line)),
            "target_file": str(path),
            "line_range": [line, line],
            "faults": ["SYNTAX"],
            "surgeon_directive": f"{path.name}:{line}: {message}",
        }

    def _add_unparsed(self, report: dict[str, Any], path: Path, exc: SyntaxError) -> None:
        report.setdefault("unparsed", []).append(
            {"file": str(path), "line": exc.lineno or 1, "fault": "SYNTAX", "message": exc.msg or "does not parse"}
        )
        report["closer_warrants"].append(self._unparsed_warrant(path, exc))
        report["warrant_count"] = len(report["closer_warrants"])
        report["is_sealed"] = False

    def _unparsed_only(self, path: Path, exc: SyntaxError) -> dict[str, Any]:
        expected = self.cartouche["expected_full_bitmask"]
        report = {
            "domain_id": self.cartouche["domain_id"],
            "cartouche_sha256": self.cartouche["cartouche_sha256"],
            "is_sealed": False,
            "waiting": False,
            "projection_residual": 0.0,
            "active_bitmask": 0,
            "expected_bitmask": expected,
            "missing_bitmask_delta": expected,
            "glyph_diagnostics": {},
            "broken_edges": [],
            "warrant_count": 0,
            "closer_warrants": [],
            "target": str(path),
        }
        self._add_unparsed(report, path, exc)
        return report

    def _project(
        self,
        extractor: ASTTopologyExtractor,
        where: Callable[[str], Path],
        fallback: Path,
    ) -> dict[str, Any]:
        def home(name: str | None) -> Path:
            if name and name in extractor.defined_functions:
                return where(name)
            return fallback

        active_bitmask = 0
        glyph_diagnostics: dict[str, dict[str, Any]] = {}
        warrants: list[dict[str, Any]] = []
        sub_glyphs: dict[str, dict[str, Any]] = self.cartouche["sub_glyphs"]

        for fxn_name, glyph_meta in sub_glyphs.items():
            fxn_info = extractor.defined_functions.get(fxn_name)
            located = home(fxn_name)
            if fxn_info is None:
                glyph_diagnostics[fxn_name] = {
                    "fidelity": 0.0,
                    "faults": ["MISSING_FUNCTION"],
                }
                warrants.append(
                    {
                        "warrant_type": "CARTOUCHE_MISSING_GLYPH",
                        "double_jeopardy_hash": self._build_warrant_hash(
                            located.name, "MISSING_GLYPH", fxn_name
                        ),
                        "target_file": str(located),
                        "line_range": [1, 1],
                        "missing_primitive": fxn_name,
                        "cartouche_region": glyph_meta["sign_name"],
                        "required_signal_hash": glyph_meta["signal_hash"],
                        "surgeon_directive": (
                            f"Implement atomic primitive '{fxn_name}' to populate "
                            f"Cartouche sign '{glyph_meta['sign_name']}'."
                        ),
                    }
                )
            elif fxn_info["is_stub"]:
                glyph_diagnostics[fxn_name] = {
                    "fidelity": 0.0,
                    "faults": ["HOLLOW_STUB"],
                }
                warrants.append(
                    {
                        "warrant_type": "CARTOUCHE_COUNTERFEIT_STUB",
                        "double_jeopardy_hash": self._build_warrant_hash(
                            located.name, "COUNTERFEIT_STUB", fxn_name
                        ),
                        "target_file": str(located),
                        "line_range": [fxn_info["lineno"], fxn_info["end_lineno"]],
                        "missing_primitive": fxn_name,
                        "cartouche_region": glyph_meta["sign_name"],
                        "surgeon_directive": (
                            f"Function '{fxn_name}' at line {fxn_info['lineno']} is a hollow stub. "
                            f"Replace with concrete domain logic satisfying signal {glyph_meta['signal_hash']}."
                        ),
                    }
                )
            else:
                invariants = glyph_meta.get("required_invariants", {})
                # A sign is sealed or it is not (owner ruling 2026-10-24). Only faults the scan can be sure of
                # count: the locked parameters are gone, every return is a constant, or a bare except swallows
                # errors. A check that cannot tell (a short body may be correct) is let through, as a note.
                faults: list[str] = []
                notes: list[str] = []

                req_params = invariants.get("required_params", [])
                missing_params = [p for p in req_params if p not in fxn_info["arg_names"]]
                if missing_params:
                    faults.append(f"MISSING_PARAMS({','.join(missing_params)})")

                if invariants.get("forbid_constant_return", True) and fxn_info[
                    "only_constant_returns"
                ]:
                    faults.append("DEGENERATE_CONSTANT_RETURN")

                if invariants.get("forbid_bare_except", True) and fxn_info["has_bare_except"]:
                    faults.append("SWALLOWED_BARE_EXCEPT")

                min_density = invariants.get("min_ast_nodes", 4)
                if fxn_info["ast_density"] < min_density:
                    notes.append(f"SHORT_BODY({fxn_info['ast_density']}<{min_density}): let through")

                fidelity = 0.0 if faults else 1.0
                glyph_diagnostics[fxn_name] = {"fidelity": fidelity, "faults": faults, "notes": notes}

                if fidelity == 1.0:
                    active_bitmask |= glyph_meta["bit_mask"]
                else:
                    warrants.append(
                        {
                            "warrant_type": "CARTOUCHE_MALFORMED_GLYPH",
                            "double_jeopardy_hash": self._build_warrant_hash(
                                located.name,
                                f"MALFORMED::{','.join(sorted(faults))}",
                                fxn_name,
                            ),
                            "target_file": str(located),
                            "line_range": [fxn_info["lineno"], fxn_info["end_lineno"]],
                            "malformed_primitive": fxn_name,
                            "cartouche_region": glyph_meta["sign_name"],
                            "glyph_fidelity": fidelity,
                            "faults": faults,
                            "surgeon_directive": (
                                f"Sign '{glyph_meta['sign_name']}' ({fxn_name}) is malformed "
                                f"(fidelity={fidelity}, faults={faults}). "
                                "Remediate defects to restore 1.0 projection lock."
                            ),
                        }
                    )

        broken_edges: list[list[str]] = []

        def reaches(start: str, goal: str) -> bool:
            """goal is called from start, directly or through other functions of this build."""
            seen, stack = set(), [start]
            while stack:
                here = stack.pop()
                for a, b in extractor.call_edges:
                    if a == here and b not in seen:
                        if b == goal:
                            return True
                        seen.add(b)
                        stack.append(b)
            return False

        for caller, callee in self.cartouche["required_edges"]:
            direct_edge = (caller, callee) in extractor.call_edges
            # "Sequenced with": one function calls the caller and reaches the callee, directly or through the
            # turn function that owns the loop (owner ruling 2026-11-03: start_round -> take_turn -> ask_question).
            orchestrated_edge = any(
                (orch, caller) in extractor.call_edges and reaches(orch, callee)
                for orch in extractor.defined_functions
            )
            if direct_edge or orchestrated_edge:
                continue
            broken_edges.append([caller, callee])
            caller_home = home(caller)
            caller_line = extractor.defined_functions.get(caller, {}).get("lineno", 1)
            warrants.append(
                {
                    "warrant_type": "CARTOUCHE_TOPOLOGY_BREAK",
                    "double_jeopardy_hash": self._build_warrant_hash(
                        caller_home.name,
                        "TOPOLOGY_BREAK",
                        f"{caller}->{callee}",
                    ),
                    "target_file": str(caller_home),
                    "line_range": [caller_line, caller_line],
                    "broken_edge": [caller, callee],
                    "surgeon_directive": (
                        f"Topological invariant violation: '{caller}' must transition to "
                        f"or be sequenced with '{callee}'."
                    ),
                }
            )

        expected_mask = self.cartouche["expected_full_bitmask"]
        projection_residual = round(
            sum(1.0 - d["fidelity"] for d in glyph_diagnostics.values())
            + len(broken_edges),
            2,
        )
        is_sealed = (projection_residual == 0.0) and (active_bitmask == expected_mask)
        return {
            "domain_id": self.cartouche["domain_id"],
            "cartouche_sha256": self.cartouche["cartouche_sha256"],
            "is_sealed": is_sealed,
            "waiting": False,
            "projection_residual": projection_residual,
            "active_bitmask": active_bitmask,
            "expected_bitmask": expected_mask,
            "missing_bitmask_delta": expected_mask ^ active_bitmask,
            "glyph_diagnostics": glyph_diagnostics,
            "broken_edges": broken_edges,
            "warrant_count": len(warrants),
            "closer_warrants": warrants,
            "target": str(fallback),
        }

    def scan_and_write(self, target_py_path: Path, output_path: Path) -> dict[str, Any]:
        report = self.scan_file(target_py_path)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
