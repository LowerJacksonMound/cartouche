"""The same five defects, on whatever sign was selected. The phone chart is not special."""

from __future__ import annotations


def project_sign(svg: str, fidelity: float, broken: bool) -> str:
    """Template, locked, hazy, missing, and skew. The drawing underneath can be any sign."""

    head, rest = svg.split(">", 1)
    inner = rest.rsplit("</svg>", 1)[0]
    head = head.replace('viewBox="0 0 64 64"', 'viewBox="-8 -10 80 84"')
    blur = round((1.0 - fidelity) * 4.5, 2) if 0.0 < fidelity < 1.0 else 0.0
    if fidelity == 0.0:
        color, dash, opacity = "#ef4444", "4 3", "1"
    elif fidelity < 1.0:
        color, dash, opacity = "#d97706", "", f"{max(0.35, fidelity):.2f}"
    else:
        color, dash, opacity = "#10b981", "", "1"
    transform = ' transform="translate(6,-5) skewX(8)"' if broken else ""
    defs = (
        f'<defs><filter id="haze" x="-20%" y="-20%" width="140%" height="140%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="{blur}" /></filter></defs>'
        if blur
        else ""
    )
    haze = ' filter="url(#haze)"' if blur else ""
    ghost = (
        f'<g color="#30363d" stroke-dasharray="2 2" fill="none" opacity="0.85">{inner}</g>'
    )
    live = (
        f'<g color="{color}" stroke-dasharray="{dash}" opacity="{opacity}"{haze}{transform}>{inner}</g>'
    )
    return f"{head}>{defs}{ghost}{live}</svg>"


# ---- the five defect words ---------------------------------------------------------
#
# INTENT.md: "The scan has five defects: template, locked, hazy, missing, and skew." Each word,
# on a cartouche symbol, says how the function that symbol represents is incorrect. A reported
# issue carries exactly one of them as `fault` (a file that does not parse is `SYNTAX`, as
# MCP.md says). The scanner's own codes stay on the row as `detail`, so nothing is lost.

TEMPLATE = "template"  # the function is a hollow stub: the signature, no body
LOCKED = "locked"  # the request was edited after release; the spec no longer hashes to the lock
HAZY = "hazy"  # the function is there but not clear: constant return, too thin, wrong params
MISSING = "missing"  # the function is not there
SKEW = "skew"  # a required edge is gone: the function never reaches the next one
SYNTAX = "SYNTAX"  # the file does not parse

DEFECTS: tuple[str, ...] = (TEMPLATE, LOCKED, HAZY, MISSING, SKEW)
FAULT_WORDS: frozenset[str] = frozenset(DEFECTS) | {SYNTAX}

_WARRANT_DEFECT: dict[str, str] = {
    "CARTOUCHE_MISSING_GLYPH": MISSING,
    "CARTOUCHE_COUNTERFEIT_STUB": TEMPLATE,
    "CARTOUCHE_TOPOLOGY_BREAK": SKEW,
    "CARTOUCHE_MALFORMED_GLYPH": HAZY,
    "CARTOUCHE_UNPARSED": SYNTAX,
}


def defect_of(warrant_type: str | None) -> str:
    """The one word for a scanner warrant. A malformed sign of any kind is hazy."""

    return _WARRANT_DEFECT.get(warrant_type or "", HAZY)


def issues_of(report: dict | None) -> list[dict]:
    """One row an agent can fix: file, function, lines, fault, detail. A sign name is not the fault."""

    if not report or report.get("waiting"):
        return []
    rows: list[dict] = []
    for warrant in report.get("closer_warrants") or []:
        kind = warrant.get("warrant_type")
        fault = defect_of(kind)
        if kind == "CARTOUCHE_MISSING_GLYPH":
            function = warrant.get("missing_primitive")
            detail = "MISSING_FUNCTION"
        elif kind == "CARTOUCHE_COUNTERFEIT_STUB":
            function = warrant.get("missing_primitive")
            detail = "HOLLOW_STUB"
        elif kind == "CARTOUCHE_TOPOLOGY_BREAK":
            edge = warrant.get("broken_edge") or [None, None]
            function = edge[0]
            detail = f"TOPOLOGY_BREAK({edge[0]}->{edge[1]})"
        elif kind == "CARTOUCHE_UNPARSED":
            function = None
            detail = SYNTAX
        else:
            function = warrant.get("malformed_primitive")
            codes = warrant.get("faults") or []
            detail = ", ".join(codes) if codes else str(kind)
        rows.append(
            {
                "file": warrant.get("target_file"),
                "function": function,
                "lines": warrant.get("line_range"),
                "fault": fault,
                "detail": detail,
                "sign": warrant.get("cartouche_region"),
                "directive": warrant.get("surgeon_directive"),
                "warrant_type": kind,
            }
        )
    return rows


def issue_line(row: dict) -> str:
    """The same row as one line of CLI output. The word first, the scanner's codes last."""

    parts = [f"fault={row.get('fault')}"]
    if row.get("function"):
        parts.append(f"function={row['function']}")
    if row.get("file"):
        parts.append(f"file={row['file']}")
    if row.get("sign"):
        parts.append(f"sign={row['sign']}")
    lines = row.get("lines")
    if lines:
        parts.append(f"lines={lines[0]}-{lines[-1]}")
    if row.get("detail"):
        parts.append(f"detail={row['detail']}")
    return " ".join(parts)
