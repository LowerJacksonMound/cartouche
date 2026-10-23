"""Headless gate. Exit 0 only when the projection residual is exactly 0."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cartouche.broll_fetcher import BRollFetcher
from cartouche.build_release import release
from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.cartouche_image import render_cartouche
from cartouche.cartouche_scanner import CartoucheScanner
from cartouche.clip_library import LibraryFiller, approve, load_dictionary, save_dictionary, view
from cartouche.hold import hold
from cartouche.instantiate import instantiate
from cartouche.lock_build import lock_cartouche
from cartouche.macro_library import admit, compose, load_shelf, save_shelf
from cartouche.project_symbol import LOCKED, issue_line
from cartouche.symbols import mark_cartouche
from cartouche.resolve import resolve_phrase
from cartouche.selftest import selftest
from cartouche.sequence import project_sequence
from cartouche.session import run_session, stop_path
from cartouche.signal_stitcher import SignalStitcher


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_compile(track_path: Path, out_path: Path) -> int:
    master = CartoucheCompiler(_load(track_path)).compile_cartouche(out_path)
    print(master["cartouche_sha256"])
    return 0


def cmd_scan(cartouche_path: Path, target: Path, out_path: Path, svg_path: Path | None) -> int:
    master = _load(cartouche_path)
    report = CartoucheScanner(master).scan_and_write(target, out_path)
    if svg_path is not None:
        CartoucheCompiler.render_svg(
            master,
            report["glyph_diagnostics"],
            report["broken_edges"],
            svg_path,
        )
    print(
        f"sealed={str(report['is_sealed']).lower()} residual={report['projection_residual']:.2f} "
        f"warrants={report['warrant_count']}"
    )
    return 0 if report["is_sealed"] else 2


def cmd_stitch(spec_path: Path, out_dir: Path, mp4: bool) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    track = SignalStitcher(_load(spec_path), base_dir=spec_path.parent).compile_montage_and_signals(
        concat_list_path=out_dir / "concat.txt",
        signal_track_path=out_dir / "certified_signal_track.json",
        output_mp4_path=(out_dir / "rehearsal.mp4") if mp4 else None,
    )
    print(
        f"permutations={track['total_permutations']} montage={track['montage_status']} "
        f"edges={len(track['required_edges'])}"
    )
    return 0


def cmd_fetch(spec_path: Path, out_path: Path | None, library: Path | None) -> int:
    if out_path is None:
        out_path = spec_path.with_name(spec_path.stem + ".fetch.json")
    report = BRollFetcher(
        _load(spec_path), base_dir=spec_path.parent, library=library
    ).write(out_path)
    counts = report["counts"]
    print(
        f"sought={counts['sought']} found={counts['found']} "
        f"missing={counts['missing']} undeclared={counts['undeclared']} "
        f"unreached={counts['unreached']}"
    )
    return 0


def cmd_fill(spec_path: Path, out_path: Path) -> int:
    dictionary, report = LibraryFiller().fill(_load(spec_path), load_dictionary(out_path))
    save_dictionary(out_path, dictionary)
    counts = report["counts"]
    print(
        f"interaction={report['interaction']} pending={counts['pending']} "
        f"approved={counts['approved']} reused={counts['reused']} "
        f"paths={counts['paths_covered']}/{counts['paths']}"
    )
    return 0


def cmd_view(dictionary_path: Path, interaction: str, phrase: str, base: Path, node: str | None) -> int:
    dictionary = load_dictionary(dictionary_path)
    before = json.dumps(dictionary)
    result = view(dictionary, interaction, phrase, base, node_id=node)
    if not result["seen"]:
        if json.dumps(dictionary) != before:
            raise RuntimeError("view stored a missing clip")
        print(f"seen=false reason={result.get('reason', 'unseen')}")
        return 2
    save_dictionary(dictionary_path, dictionary)
    print("seen=true")
    return 0


def cmd_approve(dictionary_path: Path, interaction: str, phrase: str, base: Path, node: str | None) -> int:
    dictionary = load_dictionary(dictionary_path)
    before = json.dumps(dictionary)
    entry = approve(dictionary, interaction, phrase, base, node_id=node)
    reason = entry.get("reason")
    if reason == "unseen":
        if json.dumps(dictionary) != before:
            raise RuntimeError("approve locked a clip that was not seen")
        print("approved=false reason=unseen")
        return 2
    if reason == "ambiguous":
        if json.dumps(dictionary) != before:
            raise RuntimeError("approve locked an ambiguous clip")
        print("approved=false reason=ambiguous")
        return 2
    if reason == "replaced":
        save_dictionary(dictionary_path, dictionary)
        print("approved=false reason=replaced")
        return 2
    save_dictionary(dictionary_path, dictionary)
    print(f"approved {entry['phrase_key']}")
    return 0


def cmd_release(spec_path: Path, dictionary_path: Path, out_path: Path) -> int:
    contract = release(_load(spec_path), load_dictionary(dictionary_path), spec_path.parent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    print(
        f"released={str(contract['released']).lower()} "
        f"paths={contract['paths_covered']}/{contract['paths']} "
        f"files={str(contract['files_present']).lower()}"
    )
    if not contract["released"]:
        # An open path names the lines that block, one per line. The lock is in the file, not here.
        for line in contract["blocks"]:
            print(f"block: {line}")
        return 2
    print(contract["cartouche_sha256"])
    return 0


def cmd_hold(spec_path: Path, contract_path: Path, target: Path, out_path: Path) -> int:
    contract_text = contract_path.read_text(encoding="utf-8")
    result = hold(_load(spec_path), json.loads(contract_text), target, spec_path.parent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if contract_path.read_text(encoding="utf-8") != contract_text:
        raise RuntimeError("hold rewrote the release")
    if not result["scanned"]:
        if result["reason"] == "intent":
            print(f"held=false reason=intent fault={LOCKED}")
        else:
            print(f"held=false reason={result['reason']}")
        return 2
    print(
        f"held=true sealed={str(result['is_sealed']).lower()} "
        f"residual={result['projection_residual']:.2f} warrants={result['warrant_count']}"
    )
    for row in result.get("issues") or []:
        print(f"issue: {issue_line(row)}")
    return 0 if result["is_sealed"] else 2


def cmd_sequence(spec_path: Path, target: Path, out_path: Path) -> int:
    spec = _load(spec_path)
    track = SignalStitcher(spec, base_dir=spec_path.parent).compile_montage_and_signals()
    master = CartoucheCompiler(track).compile_cartouche()
    report = CartoucheScanner(master).scan_file(target)
    result = project_sequence(spec, master, report, target)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    state = "held" if result["order_held"] else "broken"
    print(f"order={state} cartouches={result['sealed_count']}/{result['cartouche_count']}")
    print(result["cartouche_sha256"])
    return 0 if result["complete"] else 2


def cmd_admit(sequence_path: Path, out_path: Path) -> int:
    shelf = load_shelf(out_path)
    before = json.dumps(shelf)
    entry = admit(shelf, _load(sequence_path))
    if entry.get("admitted") is not True:
        if json.dumps(shelf) != before:
            raise RuntimeError("admit stored an open sequence")
        print("admitted=false")
        return 2
    save_shelf(out_path, shelf)
    print(f"admitted=true symbols={len(entry['symbols'])}")
    print(entry["cartouche_sha256"])
    return 0


def cmd_compose(image_path: Path, shelf_path: Path, out_path: Path) -> int:
    shelf_text = shelf_path.read_text(encoding="utf-8") if shelf_path.is_file() else ""
    result = compose(_load(image_path), load_shelf(shelf_path))
    if shelf_path.is_file() and shelf_path.read_text(encoding="utf-8") != shelf_text:
        raise RuntimeError("compose rewrote the shelf")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"complete={str(result['complete']).lower()} "
        f"symbols={sum(1 for item in result['symbols'] if item['admitted'])}/{len(result['symbols'])}"
    )
    print(result["image_sha256"])
    return 0 if result["complete"] else 2


def cmd_instantiate(spec_path: Path, request_path: Path, out_path: Path) -> int:
    spec_text = spec_path.read_text(encoding="utf-8")
    result = instantiate(_load(spec_path), _load(request_path))
    if spec_path.read_text(encoding="utf-8") != spec_text:
        raise RuntimeError("instantiate rewrote the spec")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"held={str(result['held']).lower()}")
    print(result["cartouche_sha256"])
    return 0 if result["held"] else 2


def cmd_resolve(spec_path: Path, dictionary_path: Path, phrase: str, out_path: Path | None) -> int:
    spec_text = spec_path.read_text(encoding="utf-8")
    shelf_text = dictionary_path.read_text(encoding="utf-8") if dictionary_path.is_file() else ""
    result = resolve_phrase(_load(spec_path), phrase, load_dictionary(dictionary_path))
    if spec_path.read_text(encoding="utf-8") != spec_text:
        raise RuntimeError("resolve rewrote the spec")
    if dictionary_path.is_file() and dictionary_path.read_text(encoding="utf-8") != shelf_text:
        raise RuntimeError("resolve rewrote the shelf")
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"resolved={str(result['resolved']).lower()} reason={result['reason']}")
    if result["resolved"]:
        print(result["signal_lock"])
    return 0 if result["resolved"] else 2


def cmd_lock(spec_path: Path, dictionary_path: Path, out_path: Path) -> int:
    shelf_text = dictionary_path.read_text(encoding="utf-8") if dictionary_path.is_file() else ""
    result = lock_cartouche(_load(spec_path), load_dictionary(dictionary_path))
    if dictionary_path.is_file() and dictionary_path.read_text(encoding="utf-8") != shelf_text:
        raise RuntimeError("lock rewrote the shelf")
    if not result["locked"]:
        print(f"locked=false open={len(result['open'])} mismatched={len(result['mismatched'])}")
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result["cartouche"], indent=2) + "\n", encoding="utf-8")
    print("locked=true")
    print(result["cartouche"]["cartouche_sha256"])
    return 0


def cmd_mark(spec_path: Path, dictionary_path: Path, out_path: Path) -> int:
    shelf_text = dictionary_path.read_text(encoding="utf-8") if dictionary_path.is_file() else ""
    locked = lock_cartouche(_load(spec_path), load_dictionary(dictionary_path))
    if dictionary_path.is_file() and dictionary_path.read_text(encoding="utf-8") != shelf_text:
        raise RuntimeError("mark rewrote the shelf")
    if not locked["locked"]:
        print(f"marked=false open={len(locked['open'])}")
        return 2
    marked = mark_cartouche(_load(spec_path), locked["cartouche"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(marked, indent=2) + "\n", encoding="utf-8")
    names = " ".join(band["id"] for band in marked["cartouches"])
    print(f"marked=true signs={names}")
    return 0


def cmd_image(spec_path: Path, dictionary_path: Path, out_path: Path) -> int:
    shelf_text = dictionary_path.read_text(encoding="utf-8") if dictionary_path.is_file() else ""
    locked = lock_cartouche(_load(spec_path), load_dictionary(dictionary_path))
    if dictionary_path.is_file() and dictionary_path.read_text(encoding="utf-8") != shelf_text:
        raise RuntimeError("image rewrote the shelf")
    if not locked["locked"]:
        print(f"image=false open={len(locked['open'])}")
        return 2
    marked = mark_cartouche(_load(spec_path), locked["cartouche"])
    image = render_cartouche(marked)
    seals = [band["seal"] for band in image["cartouches"]]
    signs = [band["signs"] for band in image["cartouches"]]
    if seals != [band["id"] for band in marked["cartouches"]]:
        raise RuntimeError("image seals do not match the marks")
    if signs != [[{"id": item["id"], "name": item["name"]} for item in band["functions"]] for band in marked["cartouches"]]:
        raise RuntimeError("image signs do not match the marks")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(image, indent=2) + "\n", encoding="utf-8")
    print("image=true seals=" + " ".join(seals))
    return 0


def cmd_gate(track_path: Path, target: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    master = CartoucheCompiler(_load(track_path)).compile_cartouche(
        out_dir / "master_cartouche.json"
    )
    report = CartoucheScanner(master).scan_and_write(target, out_dir / "scan_report.json")
    CartoucheCompiler.render_svg(
        master,
        report["glyph_diagnostics"],
        report["broken_edges"],
        out_dir / "cartouche.svg",
    )
    print(
        f"sealed={str(report['is_sealed']).lower()} residual={report['projection_residual']:.2f} "
        f"warrants={report['warrant_count']}"
    )
    return 0 if report["is_sealed"] else 2


def cmd_start(spec_path: Path, contract_path: Path, target: Path, session_path: Path) -> int:
    contract_text = contract_path.read_text(encoding="utf-8")
    code = run_session(
        _load(spec_path), json.loads(contract_text), target, session_path, spec_path.parent
    )
    if contract_path.read_text(encoding="utf-8") != contract_text:
        raise RuntimeError("start rewrote the release")
    return code


def cmd_stop(session_path: Path) -> int:
    flag = stop_path(session_path)
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("stop\n", encoding="utf-8")
    print("stopping")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cartouche")
    sub = parser.add_subparsers(dest="cmd", required=True)

    compile_p = sub.add_parser("compile")
    compile_p.add_argument("track", type=Path)
    compile_p.add_argument("-o", "--out", type=Path, required=True)

    scan_p = sub.add_parser("scan")
    scan_p.add_argument("cartouche", type=Path)
    scan_p.add_argument("target", type=Path)
    scan_p.add_argument("-o", "--out", type=Path, required=True)
    scan_p.add_argument("--svg", type=Path)

    gate_p = sub.add_parser("gate")
    gate_p.add_argument("track", type=Path)
    gate_p.add_argument("target", type=Path)
    gate_p.add_argument("-o", "--out", type=Path, required=True)

    stitch_p = sub.add_parser("stitch")
    stitch_p.add_argument("spec", type=Path)
    stitch_p.add_argument("-o", "--out", type=Path, required=True)
    stitch_p.add_argument("--mp4", action="store_true")

    fetch_p = sub.add_parser("fetch", help="walk the chart; list every box a path can reach")
    fetch_p.add_argument("spec", type=Path)
    fetch_p.add_argument(
        "-o", "--out", type=Path, help="report path (default: <spec stem>.fetch.json beside the spec)"
    )
    fetch_p.add_argument(
        "--library",
        type=Path,
        help="an extra folder of <token_id>.mp4 clips to look in, after the spec's declared path "
        "and the shelf path library/<interaction>/<digest>.mp4 beside the spec",
    )

    fill_p = sub.add_parser("fill")
    fill_p.add_argument("spec", type=Path)
    fill_p.add_argument("-o", "--out", type=Path, required=True)

    base_help = (
        "folder the shelf's clip_path (library/<interaction>/<digest>.mp4) is relative to "
        "(default: the folder you run in)"
    )
    node_help = (
        "node id that picks the clip when the same words are on more than one entry "
        "(an edge case has its own clip)"
    )
    approve_p = sub.add_parser("approve", help="sign off a viewed clip; writes its signal lock")
    approve_p.add_argument("dictionary", type=Path)
    approve_p.add_argument("--interaction", required=True)
    approve_p.add_argument("--phrase", required=True)
    approve_p.add_argument("--base", type=Path, default=Path("."), help=base_help)
    approve_p.add_argument("--node", help=node_help)

    view_p = sub.add_parser("view", help="record the bytes of a clip that were seen")
    view_p.add_argument("dictionary", type=Path)
    view_p.add_argument("--interaction", required=True)
    view_p.add_argument("--phrase", required=True)
    view_p.add_argument("--base", type=Path, default=Path("."), help=base_help)
    view_p.add_argument("--node", help=node_help)

    release_p = sub.add_parser("release")
    release_p.add_argument("spec", type=Path)
    release_p.add_argument("dictionary", type=Path)
    release_p.add_argument("-o", "--out", type=Path, required=True)

    hold_p = sub.add_parser("hold")
    hold_p.add_argument("spec", type=Path)
    hold_p.add_argument("contract", type=Path)
    hold_p.add_argument("target", type=Path)
    hold_p.add_argument("-o", "--out", type=Path, required=True)

    sequence_p = sub.add_parser("sequence")
    sequence_p.add_argument("spec", type=Path)
    sequence_p.add_argument("target", type=Path)
    sequence_p.add_argument("-o", "--out", type=Path, required=True)

    admit_p = sub.add_parser("admit")
    admit_p.add_argument("sequence", type=Path)
    admit_p.add_argument("-o", "--out", type=Path, required=True)

    compose_p = sub.add_parser("compose")
    compose_p.add_argument("image", type=Path)
    compose_p.add_argument("shelf", type=Path)
    compose_p.add_argument("-o", "--out", type=Path, required=True)

    instantiate_p = sub.add_parser("instantiate")
    instantiate_p.add_argument("spec", type=Path)
    instantiate_p.add_argument("request", type=Path)
    instantiate_p.add_argument("-o", "--out", type=Path, required=True)

    resolve_p = sub.add_parser("resolve")
    resolve_p.add_argument("spec", type=Path)
    resolve_p.add_argument("dictionary", type=Path)
    resolve_p.add_argument("--phrase", required=True)
    resolve_p.add_argument("-o", "--out", type=Path)

    lock_p = sub.add_parser("lock")
    lock_p.add_argument("spec", type=Path)
    lock_p.add_argument("dictionary", type=Path)
    lock_p.add_argument("-o", "--out", type=Path, required=True)

    mark_p = sub.add_parser("mark")
    mark_p.add_argument("spec", type=Path)
    mark_p.add_argument("dictionary", type=Path)
    mark_p.add_argument("-o", "--out", type=Path, required=True)

    image_p = sub.add_parser("image")
    image_p.add_argument("spec", type=Path)
    image_p.add_argument("dictionary", type=Path)
    image_p.add_argument("-o", "--out", type=Path, required=True)

    start_p = sub.add_parser("start")
    start_p.add_argument("spec", type=Path)
    start_p.add_argument("contract", type=Path)
    start_p.add_argument("target", type=Path)
    start_p.add_argument("--session", type=Path, required=True)

    stop_p = sub.add_parser("stop")
    stop_p.add_argument("session", type=Path)

    sub.add_parser("selftest", help="unit tests, then one client's pass over the CLI, the stdio server and the plants")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            return cmd_compile(args.track, args.out)
        if args.cmd == "scan":
            return cmd_scan(args.cartouche, args.target, args.out, args.svg)
        if args.cmd == "stitch":
            return cmd_stitch(args.spec, args.out, args.mp4)
        if args.cmd == "fetch":
            return cmd_fetch(args.spec, args.out, args.library)
        if args.cmd == "fill":
            return cmd_fill(args.spec, args.out)
        if args.cmd == "approve":
            return cmd_approve(args.dictionary, args.interaction, args.phrase, args.base, args.node)
        if args.cmd == "view":
            return cmd_view(args.dictionary, args.interaction, args.phrase, args.base, args.node)
        if args.cmd == "release":
            return cmd_release(args.spec, args.dictionary, args.out)
        if args.cmd == "hold":
            return cmd_hold(args.spec, args.contract, args.target, args.out)
        if args.cmd == "sequence":
            return cmd_sequence(args.spec, args.target, args.out)
        if args.cmd == "admit":
            return cmd_admit(args.sequence, args.out)
        if args.cmd == "compose":
            return cmd_compose(args.image, args.shelf, args.out)
        if args.cmd == "instantiate":
            return cmd_instantiate(args.spec, args.request, args.out)
        if args.cmd == "resolve":
            return cmd_resolve(args.spec, args.dictionary, args.phrase, args.out)
        if args.cmd == "lock":
            return cmd_lock(args.spec, args.dictionary, args.out)
        if args.cmd == "mark":
            return cmd_mark(args.spec, args.dictionary, args.out)
        if args.cmd == "image":
            return cmd_image(args.spec, args.dictionary, args.out)
        if args.cmd == "start":
            return cmd_start(args.spec, args.contract, args.target, args.session)
        if args.cmd == "stop":
            return cmd_stop(args.session)
        if args.cmd == "selftest":
            return selftest()
        return cmd_gate(args.track, args.target, args.out)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"cartouche: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
