"""Gather: the AI step before sign-off. Cartouche itself calls no model.

The agent (Claude Code, through the MCP tools) does the finding. Cartouche checks and records:

  draft   the agent turns the plain app request into a chart. `check_chart` refuses a chart the
          compilers would refuse, before anything is fetched.
  seek    `wanted` lists every line a path reaches that has no signed clip: its function, whether it
          is an edge case, and how many candidates it already has.
  offer   the agent searches a source and offers a clip by URL. `offer` downloads it into that line's
          candidates folder, refuses anything that is not video, and records where it came from and
          under what licence.
  drop    rendered clips can also arrive by folder: wanted makes incoming/<function>/ for every line,
          and sweep_incoming offers anything dropped there (by the person, a subagent that renders
          scenes, or a video generator). A sidecar <clip>.json may give why, licence, title, author.
  choose  the person watches the candidates and picks one. `choose` copies it into the line's shelf
          slot. Then Cartouche's own `view` and `approve` sign it off, exactly as before.

After `approve` there is no AI anywhere: the lock, the scan and the watch are plain code.
Candidates live beside the shelf under candidates/<interaction>/<16 hex of the phrase key>/. They are never hashed;
only the clip a person signs off is.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cartouche.broll_fetcher import BRollFetcher, phrase_key
from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.clip_library import LibraryFiller, empty_dictionary, load_dictionary, save_dictionary
from cartouche.signal_stitcher import SignalStitcher
from cartouche.symbols import mark_cartouche

SOURCES = ("youtube", "archive", "pexels", "file")


def ytdlp(*args: str) -> list[str]:
    """A yt-dlp command. Set CARTOUCHE_YTDLP_COOKIES to "browser:chrome" (or another browser) or to a
    cookies.txt path to send your YouTube login, which avoids most rate limits. Off by default."""

    import os

    cmd = ["yt-dlp", "--no-warnings", "--retries", "5", "--socket-timeout", "15"]
    cookies = os.environ.get("CARTOUCHE_YTDLP_COOKIES", "").strip()
    if cookies.startswith("browser:"):
        cmd += ["--cookies-from-browser", cookies.split(":", 1)[1]]
    elif cookies:
        cmd += ["--cookies", str(Path(cookies).expanduser())]
    return cmd + list(args)
MAX_SECONDS = 20.0
_REQUIRED = ("domain_id", "interaction", "cartouche_capacity", "root_id", "nodes", "b_roll_atoms", "primitive_params")


def candidates_dir(base: Path, interaction: str, phrase: str) -> Path:
    """candidates/<interaction>/<16 hex of the phrase key>/, so a folder name is safe in a URL."""

    return base / "candidates" / interaction / hashlib.sha256(phrase_key(phrase).encode()).hexdigest()[:16]


VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def incoming_dir(base: Path, function: str) -> Path:
    """Where rendered clips for one line are dropped: incoming/<function>/."""

    return base / "incoming" / function


def sweep_incoming(spec: dict[str, Any], base: Path) -> list[dict[str, Any]]:
    """Offer every clip dropped into incoming/<function>/ that has not been offered yet.

    A file is taken once per content: the ledger incoming/.taken.json maps path, size and mtime to the
    candidate it became, so a sweep on every page poll only opens new files.
    """

    root = base / "incoming"
    if not root.is_dir():
        return []
    ledger_path = root / ".taken.json"
    ledger: dict[str, Any] = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else {}
    phrase_of = {}
    for node in spec["nodes"].values():
        atom = spec["b_roll_atoms"].get(node.get("token_id"), {})
        phrase_of.setdefault(node["primitive_fxn"], atom.get("phrase", ""))
    taken: list[dict[str, Any]] = []
    for function, phrase in phrase_of.items():
        folder = incoming_dir(base, function)
        if not folder.is_dir():
            continue
        for clip in sorted(folder.iterdir()):
            if clip.suffix.lower() not in VIDEO_SUFFIXES or clip.name.startswith("."):
                continue
            stat = clip.stat()
            key = f"{clip.relative_to(base)}|{stat.st_size}|{int(stat.st_mtime)}"
            if key in ledger:
                continue
            if time.time() - stat.st_mtime < 2:  # still being written
                continue
            side = clip.with_suffix(".json")
            meta = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
            seconds = min(_probe(clip).get("seconds") or 0.0, MAX_SECONDS)
            if seconds <= 0:
                ledger[key] = {"offered": False, "reason": "not playable video"}
                continue
            record = offer(
                spec, base, phrase, "file", str(clip), float(meta.get("start", 0.0)), float(meta.get("seconds", seconds)),
                str(meta.get("why", f"dropped into incoming/{function}/")),
                str(meta.get("licence", "yours: dropped into the incoming folder")),
            )
            if record.get("offered"):
                for field in ("title", "author"):
                    if meta.get(field):
                        record[field] = meta[field]
                cand = candidates_dir(base, spec["interaction"], phrase) / f"{record['id']}.json"
                saved = json.loads(cand.read_text(encoding="utf-8"))
                saved.update({k: record[k] for k in ("title", "author") if k in record})
                saved["dropped"] = str(clip.relative_to(base))
                cand.write_text(json.dumps(saved, indent=1) + "\n", encoding="utf-8")
            ledger[key] = {"offered": bool(record.get("offered")), "id": record.get("id"), "reason": record.get("reason")}
            taken.append({"function": function, "file": clip.name, **{k: record.get(k) for k in ("offered", "id", "reason")}})
    if taken:
        ledger_path.write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8")
    return taken


def heard_clip(base: Path, heard: str) -> Path:
    """Where a voiced line of the other party is kept: heard/<16 hex>.mp4. Never signed, never hashed as a clip."""

    return base / "heard" / (hashlib.sha256(heard.strip().encode()).hexdigest()[:16] + ".mp4")


# ---------------------------------------------------------------- draft


def check_chart(spec: dict[str, Any], base: Path | None = None) -> dict[str, Any]:
    """Refuse a chart the compilers would refuse. Writes nothing."""

    problems: list[str] = []
    for key in _REQUIRED:
        if key not in spec:
            problems.append(f"missing {key}")
    if problems:
        return {"ok": False, "problems": problems}
    atoms, nodes = spec["b_roll_atoms"], spec["nodes"]
    for node_id, node in nodes.items():
        token = node.get("token_id")
        if token not in atoms:
            problems.append(f"node {node_id}: token {token!r} has no b_roll_atoms entry")
        elif not str(atoms[token].get("phrase", "")).strip():
            problems.append(f"node {node_id}: token {token!r} has no phrase")
        elif not str(atoms[token].get("clip_path", "")).strip():
            problems.append(f"node {node_id}: token {token!r} has no clip_path (e.g. clips/{token}.mp4)")
        fxn = node.get("primitive_fxn")
        if fxn not in spec["primitive_params"]:
            problems.append(f"node {node_id}: {fxn!r} has no primitive_params entry")
        for branch in node.get("branches", []):
            if branch.get("target_node") not in nodes:
                problems.append(f"node {node_id}: branch to {branch.get('target_node')!r}, not a node")
            if "heard" in branch and not (isinstance(branch["heard"], str) and branch["heard"].strip()):
                problems.append(f"node {node_id}: a branch's heard must be the other party's line, as text")
    uses_heard = any("heard" in b for n in nodes.values() for b in n.get("branches", []))
    if uses_heard:
        for node_id, node in nodes.items():
            branches = node.get("branches", [])
            if len(branches) > 1 and any(not str(b.get("heard", "")).strip() for b in branches):
                problems.append(f"node {node_id}: {len(branches)} branches, so each needs heard (what the other party says to lead there)")
    if spec["root_id"] not in nodes:
        problems.append(f"root_id {spec['root_id']!r} is not a node")
    if problems:
        return {"ok": False, "problems": problems}
    try:
        master = CartoucheCompiler(
            SignalStitcher(spec, base_dir=base or Path(".")).compile_montage_and_signals()
        ).compile_cartouche()
        marked = mark_cartouche(spec, master)
    except (ValueError, KeyError) as error:
        return {"ok": False, "problems": [f"{type(error).__name__}: {error}"]}
    fetch = BRollFetcher(spec, base_dir=base or Path(".")).fetch()
    return {
        "ok": True,
        "problems": [],
        "lines": fetch["counts"]["sought"],
        "edge_cases": sum(1 for node in nodes.values() if node.get("is_edge_case")),
        "paths": len(BRollFetcher(spec, base_dir=base or Path(".")).rehearsal_paths()),
        "functions": len(master["sub_glyphs"]),
        "signs": [
            {"part": band["name"], "seal": band["id"], "signs": [f["id"] for f in band["functions"]]}
            for band in marked["cartouches"]
        ],
    }


# ---------------------------------------------------------------- seek


def wanted(spec: dict[str, Any], dictionary_path: Path, base: Path) -> dict[str, Any]:
    """Every line a path reaches, with what it stands for and how far its clip has got.

    It runs `fill` first, so every line has its shelf slot, and makes each line's incoming/<function>/
    drop folder with a LINE.txt naming the line.
    """

    dictionary = load_dictionary(dictionary_path) if dictionary_path.is_file() else empty_dictionary()
    dictionary, report = LibraryFiller().fill(spec, dictionary)
    save_dictionary(dictionary_path, dictionary)
    shelf = dictionary["interactions"][spec["interaction"]]
    lines = []
    for sought in BRollFetcher(spec, base_dir=base).fetch()["sought"]:
        node = spec["nodes"][sought["node_id"]]
        phrase = sought["phrase"]
        entry = next((e for e in shelf.values() if e.get("phrase") == phrase), {})
        folder = candidates_dir(base, spec["interaction"], phrase)
        offered = sorted(p.name for p in folder.glob("*.json")) if folder.is_dir() else []
        drop = incoming_dir(base, node["primitive_fxn"])
        drop.mkdir(parents=True, exist_ok=True)
        note = drop / "LINE.txt"
        if not note.is_file():
            note.write_text(f"{phrase}\n\nDrop rendered clips for this line here (.mp4 .mov .m4v .webm .mkv, up to {MAX_SECONDS:g} s used).\n"
                            "Optional sidecar <clip>.json: why, licence, title, author, start, seconds.\n", encoding="utf-8")
        lines.append(
            {
                "node_id": sought["node_id"],
                "phrase": phrase,
                "function": node["primitive_fxn"],
                "edge_case": bool(node.get("is_edge_case")),
                "status": entry.get("status", "pending"),
                "slot": entry.get("clip_path"),
                "candidates": len(offered),
                "incoming": str(drop.relative_to(base)),
            }
        )
    phrase_of = {nid: spec["b_roll_atoms"][n["token_id"]]["phrase"] for nid, n in spec["nodes"].items()}
    for line in lines:
        node = spec["nodes"][line["node_id"]]
        line["speaker"] = spec["b_roll_atoms"][node["token_id"]].get("speaker", "")
        line["heard_next"] = [
            {"heard": b["heard"], "then": phrase_of[b["target_node"]], "voiced": heard_clip(base, b["heard"]).is_file()}
            for b in node.get("branches", []) if str(b.get("heard", "")).strip()
        ]
        line["heard_before"] = sorted({
            b["heard"] for n in spec["nodes"].values() for b in n.get("branches", [])
            if b.get("target_node") == line["node_id"] and str(b.get("heard", "")).strip()
        })
    lines = tree_order(spec, lines)
    return {
        "interaction": spec["interaction"],
        "request": spec.get("request", ""),
        "lines": lines,
        "counts": report["counts"],
    }


def tree_order(spec: dict[str, Any], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lines in decision-tree order: the main path from the root first, each edge case placed right after
    the main-path line it stands in for (the main child of the same parent). Each line says which lines it
    follows (`after`), which come next (`next`), and, for an edge case, which line it replaces (`instead_of`)."""

    nodes = spec["nodes"]
    phrase = {nid: spec["b_roll_atoms"][n["token_id"]]["phrase"] for nid, n in nodes.items()}
    parents: dict[str, list[str]] = {nid: [] for nid in nodes}
    for nid, node in nodes.items():
        for branch in node.get("branches", []):
            parents[branch["target_node"]].append(nid)
    kids = {nid: [b["target_node"] for b in node.get("branches", [])] for nid, node in nodes.items()}
    main: list[str] = []
    nid: str | None = spec["root_id"]
    while nid is not None and nid not in main:
        main.append(nid)
        nid = next((k for k in kids[nid] if not nodes[k].get("is_edge_case")), None)
    order = list(main)
    instead: dict[str, str] = {}
    pending = [n for n in nodes if n not in main]
    while pending:
        placed = False
        for nid in list(pending):
            parent = next((p for p in parents[nid] if p in order), None)
            if parent is None:
                continue
            sibling = next((k for k in kids[parent] if k in main and k != nid), None)
            if sibling:  # another thing that could be said instead: after the main line and its alternatives
                instead[nid] = sibling
                at = order.index(sibling) + 1
                while at < len(order) and order[at] not in main:  # past earlier alternatives and their replies
                    at += 1
            else:  # the reply to an alternative: right after it
                at = order.index(parent) + 1
            order.insert(at, nid)
            pending.remove(nid)
            placed = True
        if not placed:
            order.extend(pending)
            break
    step = {nid: i + 1 for i, nid in enumerate(order)}
    by_phrase = {p: nid for nid, p in phrase.items()}
    for line in lines:
        nid = by_phrase.get(line["phrase"], line.get("node_id"))
        line["step"] = step.get(nid, len(step) + 1)
        line["after"] = [phrase[p] for p in parents.get(nid, [])]
        line["next"] = [phrase[k] for k in kids.get(nid, [])]
        line["instead_of"] = phrase[instead[nid]] if nid in instead else None
    return sorted(lines, key=lambda line: line["step"])


def _reaches(nodes: dict[str, Any], start: str, goal: str) -> bool:
    stack, seen = [start], set()
    while stack:
        nid = stack.pop()
        if nid == goal:
            return True
        if nid in seen:
            continue
        seen.add(nid)
        stack.extend(b["target_node"] for b in nodes[nid].get("branches", []))
    return False


# ---------------------------------------------------------------- offer


def _probe(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return {"video": False}
    info = json.loads(out.stdout or "{}")
    video = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    return {
        "video": bool(video),
        "seconds": float(info.get("format", {}).get("duration") or 0.0),
        "width": video[0].get("width") if video else None,
        "height": video[0].get("height") if video else None,
    }


# Plain HTTPS H.264 first: an HLS stream (often VP9 in an mp4 wrapper) cannot be cut by section.
YT_FORMAT = (
    "bv*[height<=720][vcodec^=avc1][protocol^=https]+ba[ext=m4a][protocol^=https]"
    "/b[height<=720][vcodec^=avc1][protocol^=https]/bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]"
)


def _fetch_youtube(url: str, start: float, seconds: float, out: Path) -> dict[str, Any]:
    meta = subprocess.run(
        ytdlp("--skip-download", "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(license)s\t%(webpage_url)s", url),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if meta.returncode != 0:
        raise ValueError(f"yt-dlp could not read {url}: {meta.stderr.strip()[-200:]}")
    vid, title, uploader, licence, page = (meta.stdout.strip().splitlines()[-1].split("\t") + [""] * 5)[:5]
    # The search listing can show YouTube's translated title; the original is only known here, before the cut.
    if not english_title(title):
        raise ValueError(f"not offered: the video's title is in another script ({title[:60]})")
    got = subprocess.run(
        ytdlp(
            "-q", "-f", YT_FORMAT,
            "--download-sections", f"*{start:.2f}-{start + seconds:.2f}", "--force-keyframes-at-cuts",
            "--merge-output-format", "mp4", "-o", str(out.with_suffix(".%(ext)s")), url,
        ),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if got.returncode != 0:
        raise ValueError(f"yt-dlp could not cut {url}: {got.stderr.strip()[-200:]}")
    licence = licence if licence and licence not in ("NA", "None") else "Standard YouTube License: no reuse without the owner's permission"
    return {"title": title, "author": uploader, "licence": licence, "page": page or url, "source_id": vid}


def _fetch_http(url: str, out: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "cartouche-gather"})
    with urllib.request.urlopen(request, timeout=120) as response, out.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _trim(src: Path, start: float, seconds: float, out: Path) -> None:
    done = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(src), "-t", f"{seconds:.2f}",
         "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(out)],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise ValueError(f"ffmpeg could not cut the clip: {done.stderr.strip()[-200:]}")


def _archive_meta(url: str) -> dict[str, Any]:
    match = re.search(r"archive\.org/(?:details|download)/([^/?#]+)", url)
    if not match:
        return {"page": url}
    ident = match.group(1)
    try:
        with urllib.request.urlopen(f"https://archive.org/metadata/{ident}", timeout=60) as response:
            meta = json.loads(response.read()).get("metadata", {})
    except (OSError, ValueError):
        meta = {}
    return {
        "title": meta.get("title", ident),
        "author": meta.get("creator", ""),
        "licence": meta.get("licenseurl", "") or meta.get("rights", "") or "not stated",
        "page": f"https://archive.org/details/{ident}",
        "source_id": ident,
    }


def offer(
    spec: dict[str, Any],
    base: Path,
    phrase: str,
    source: str,
    url: str,
    start: float = 0.0,
    seconds: float = 6.0,
    why: str = "",
    licence: str = "",
) -> dict[str, Any]:
    """Download one candidate clip for one line. Refuses a line not on the chart, and anything not video."""

    if source not in SOURCES:
        return {"offered": False, "reason": f"source must be one of {', '.join(SOURCES)}"}
    if not 0 < seconds <= MAX_SECONDS:
        return {"offered": False, "reason": f"seconds must be more than 0 and at most {MAX_SECONDS:g}"}
    phrases = {s["phrase"] for s in BRollFetcher(spec, base_dir=base).fetch()["sought"]}
    if phrase not in phrases:
        return {"offered": False, "reason": "that line is not on any path of this chart"}
    folder = candidates_dir(base, spec["interaction"], phrase)
    folder.mkdir(parents=True, exist_ok=True)
    stem = hashlib.sha256(f"{source}|{url}|{start:.2f}|{seconds:.2f}".encode()).hexdigest()[:12]
    clip = folder / f"{stem}.mp4"
    meta: dict[str, Any] = {"page": url}
    try:
        if source == "youtube":
            meta = _fetch_youtube(url, start, seconds, clip)
        else:
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / "raw"
                if source == "file":
                    shutil.copyfile(Path(url).expanduser(), raw)
                    meta = {"page": str(Path(url).expanduser()), "title": Path(url).name}
                else:
                    _fetch_http(url, raw)
                    if source == "archive":
                        meta = _archive_meta(url)
                if not _probe(raw)["video"]:
                    return {"offered": False, "reason": "the file is not video"}
                _trim(raw, start, seconds, clip)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        clip.unlink(missing_ok=True)
        return {"offered": False, "reason": str(error)[:300]}
    probe = _probe(clip)
    if not probe["video"] or probe["seconds"] <= 0:
        clip.unlink(missing_ok=True)
        return {"offered": False, "reason": "the cut clip is not playable video"}
    record = {
        "id": stem,
        "phrase": phrase,
        "source": source,
        "url": url,
        "start": start,
        "seconds": round(probe["seconds"], 2),
        "width": probe["width"],
        "height": probe["height"],
        "why": why,
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "licence": licence or meta.get("licence", "not stated"),
        "page": meta.get("page", url),
        "clip": str(clip.relative_to(base)),
        "sha256": hashlib.sha256(clip.read_bytes()).hexdigest(),
        "offered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (folder / f"{stem}.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return {"offered": True, **record}


def offer_many(spec: dict[str, Any], base: Path, clips: list[dict[str, Any]], workers: int = 4) -> list[dict[str, Any]]:
    """Several offers, cut in parallel. Each clip is {phrase, source, url, start, seconds, why}."""

    from concurrent.futures import ThreadPoolExecutor

    def one(clip: dict[str, Any]) -> dict[str, Any]:
        return offer(spec, base, str(clip.get("phrase", "")), str(clip.get("source", "")), str(clip.get("url", "")),
                     float(clip.get("start", 0.0)), float(clip.get("seconds", 6.0)), str(clip.get("why", "")))

    with ThreadPoolExecutor(max(1, min(workers, 6))) as pool:
        return list(pool.map(one, clips))


def candidates(spec: dict[str, Any], base: Path, phrase: str) -> list[dict[str, Any]]:
    folder = candidates_dir(base, spec["interaction"], phrase)
    if not folder.is_dir():
        return []
    found = []
    for meta in sorted(folder.glob("*.json")):
        record = json.loads(meta.read_text(encoding="utf-8"))
        if (base / record["clip"]).is_file():
            found.append(record)
    return found


def withdraw(spec: dict[str, Any], dictionary_path: Path, base: Path, phrase: str, candidate_id: str) -> dict[str, Any]:
    """Take back an offered candidate. Refused once the line is signed off: a signed clip is the person's."""

    line = next((ln for ln in wanted(spec, dictionary_path, base)["lines"] if ln["phrase"] == phrase), None)
    if line is None:
        return {"withdrawn": False, "reason": "that line is not on any path of this chart"}
    if line["status"] in ("approved", "reused"):
        return {"withdrawn": False, "reason": "that line is signed off; its candidates stay"}
    folder = candidates_dir(base, spec["interaction"], phrase)
    meta = folder / f"{candidate_id}.json"
    if not re.fullmatch(r"[0-9a-f]{12}", candidate_id) or not meta.is_file():
        return {"withdrawn": False, "reason": "no such candidate for that line"}
    (folder / f"{candidate_id}.mp4").unlink(missing_ok=True)
    meta.unlink()
    return {"withdrawn": True, "candidate": candidate_id}


# ---------------------------------------------------------------- choose


def choose(spec: dict[str, Any], dictionary_path: Path, base: Path, phrase: str, candidate_id: str) -> dict[str, Any]:
    """Copy one candidate into the line's shelf slot. Sign-off is still view + approve."""

    found = {c["id"]: c for c in candidates(spec, base, phrase)}
    if candidate_id not in found:
        return {"chosen": False, "reason": "no such candidate for that line"}
    record = found[candidate_id]
    src = base / record["clip"]
    if hashlib.sha256(src.read_bytes()).hexdigest() != record["sha256"]:
        return {"chosen": False, "reason": "the candidate file changed after it was offered"}
    line = next((ln for ln in wanted(spec, dictionary_path, base)["lines"] if ln["phrase"] == phrase), None)
    if line is None or not line["slot"]:
        return {"chosen": False, "reason": "that line has no slot; run fill first"}
    if line["status"] == "approved":
        return {"chosen": False, "reason": "that line is already signed off"}
    slot = base / line["slot"]
    slot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, slot)
    (slot.parent / (slot.stem + ".source.json")).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return {"chosen": True, "slot": line["slot"], "candidate": candidate_id, "licence": record["licence"]}


def youtube_search_url(query: str, creative_commons: bool = True) -> str:
    """A YouTube results URL; by default filtered to Creative Commons, so the clip can be published."""

    q = urllib.parse.quote_plus(query)
    return f"https://www.youtube.com/results?search_query={q}" + ("&sp=EgIwAQ%253D%253D" if creative_commons else "")


OVERFETCH = 3  # YouTube ids listed per hit wanted; the subtitle pass then keeps the ones that can be offered
_NON_LATIN = re.compile(r"[\u0370-\u03ff\u0400-\u04ff\u0590-\u06ff\u0e00-\u0e7f\u1100-\u11ff\u3040-\u30ff\u3130-\u318f\u4e00-\u9fff\uac00-\ud7af]")


def english_title(title: str) -> bool:
    """False for a title written in another script (CJK, Cyrillic, Greek, Hebrew, Arabic, Thai, Hangul). A hit's title
    is known before anything is fetched, so a foreign-language video is dropped at no cost. An English title over
    foreign speech still gets through; the subtitle pass and the person's eyes catch that."""
    return not _NON_LATIN.search(title)


def rank_by_moment(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hits with a spoken moment first, best match first; the unsubtitled trail in YouTube's order."""
    def key(hit: dict[str, Any]) -> tuple[int, float]:
        moments = hit.get("moments") or []
        return (0, -max(m["match"] for m in moments)) if moments else (1, 0.0)
    return sorted(hits, key=key)

def search(
    source: str, query: str, limit: int = 8, creative_commons: bool = True, api_key: str = "", spoken_words: str = ""
) -> list[dict[str, Any]]:
    """Search a source and return hits the agent can offer. It does not download any video.

    With `spoken_words` (YouTube), each hit also carries `moments`: the seconds in its subtitles where
    those words are said, so a candidate can be cut where the line is actually spoken.
    """

    if source == "youtube":
        # Over-fetch: more than half of YouTube's hits carry no English subtitles and can never be offered.
        out = subprocess.run(
            ytdlp("--flat-playlist", "--playlist-end", str(limit * OVERFETCH),
                  "--print", "%(id)s\t%(duration)s\t%(title)s", youtube_search_url(query, creative_commons)),
            capture_output=True, text=True, timeout=120,
        )
        hits = []
        for line in out.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and english_title(parts[2]):
                hits.append({"url": f"https://www.youtube.com/watch?v={parts[0]}", "seconds": parts[1], "title": parts[2],
                             "licence": "Creative Commons (search filter)" if creative_commons else "check before use"})
        if not spoken_words:
            return hits[:limit]
        found = spoken_many([hit["url"] for hit in hits], spoken_words) if hits else {}
        for hit in hits:
            hit["moments"] = found[hit["url"]]["moments"]
            if found[hit["url"]].get("reason"):
                hit["subtitles"] = found[hit["url"]]["reason"]
        return rank_by_moment(hits)[:limit]
    if source == "archive":
        q = urllib.parse.quote(f"({query}) AND mediatype:(movies)")
        with urllib.request.urlopen(
            f"https://archive.org/advancedsearch.php?q={q}&fl[]=identifier&fl[]=title&fl[]=licenseurl&rows={limit}&output=json",
            timeout=60,
        ) as response:
            docs = json.loads(response.read())["response"]["docs"]
        return [{"url": f"https://archive.org/details/{d['identifier']}", "title": d.get("title", ""),
                 "licence": d.get("licenseurl", "check the item")} for d in docs]
    if source == "pexels":
        if not api_key:
            return [{"error": "pexels needs an API key (PEXELS_API_KEY)"}]
        request = urllib.request.Request(
            f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page={limit}",
            headers={"Authorization": api_key, "User-Agent": "cartouche-gather"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            videos = json.loads(response.read()).get("videos", [])
        hits = []
        for video in videos:
            files = sorted((f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"),
                           key=lambda f: abs((f.get("height") or 0) - 720))
            if files:
                hits.append({"url": files[0]["link"], "page": video.get("url"), "seconds": video.get("duration"),
                             "title": video.get("url", "").rstrip("/").split("/")[-1], "licence": "Pexels License"})
        return hits
    return [{"error": f"search source must be youtube, archive or pexels, not {source!r}"}]


# ---------------------------------------------------------------- subtitles

_CUE = re.compile(r"(\d+):(\d\d):(\d\d)\.(\d+) --> (\d+):(\d\d):(\d\d)\.(\d+)")
_WORD = re.compile(r"[a-z0-9']+")
_SMALL = set("a an and are at be but by do for from have i i'm in is it it's me my of on or so that the then this to was we what with you you're your".split())


def parse_vtt(text: str) -> list[dict[str, Any]]:
    """Cues as (start, end, text). Auto-captions repeat each line as it rolls; repeats are dropped."""

    cues: list[dict[str, Any]] = []
    seen: set[str] = set()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _CUE.search(line)
        if not match:
            continue
        g = [int(x) for x in match.groups()[:3]] + [int(match.group(4)[:3].ljust(3, "0"))]
        h = [int(x) for x in match.groups()[4:7]] + [int(match.group(8)[:3].ljust(3, "0"))]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = h[0] * 3600 + h[1] * 60 + h[2] + h[3] / 1000
        body = []
        for follow in lines[index + 1:]:
            if not follow.strip() or _CUE.search(follow):
                break
            clean = re.sub(r"<[^>]+>", "", follow).strip()
            if clean and clean not in seen:
                seen.add(clean)
                body.append(clean)
        if body:
            cues.append({"start": round(start, 2), "end": round(end, 2), "text": " ".join(body)})
    return cues


def _score(cues: list[dict[str, Any]], want: set[str], limit: int) -> list[dict[str, Any]]:
    scored = []
    for k, cue in enumerate(cues):
        window = " ".join(c["text"] for c in cues[k:k + 2]).lower()
        hit = want & set(_WORD.findall(window))
        own = want & set(_WORD.findall(cue["text"].lower()))  # the moment starts where the words start
        if own and len(hit) / len(want) >= 0.34:
            scored.append((len(hit) / len(want), cue))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["start"]))
    return [{"start": cue["start"], "text": cue["text"], "match": round(score, 2)} for score, cue in scored[:limit]]


def spoken_many(urls: list[str], words: str, limit: int = 3) -> dict[str, dict[str, Any]]:
    """Where the words are said in each video, from its subtitles. One yt-dlp run reads a list of URLs
    (-a), so every video's subtitles come down together. Keyed by URL."""

    want = set(_WORD.findall(words.lower())) - _SMALL
    if not want:
        return {u: {"moments": [], "reason": "no words to look for"} for u in urls}
    ids = {u: (re.search(r"[?&]v=([\w-]{11})", u) or re.search(r"([\w-]{11})$", u)) for u in urls}
    found: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "urls.txt"
        listing.write_text("\n".join(urls) + "\n", encoding="utf-8")
        stderr = ""
        for attempt in range(2):  # one retry: YouTube answers 429 to bursts of caption requests
            got = subprocess.run(
                ytdlp("--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "en", "--sub-format", "vtt",
                      "--sleep-subtitles", "1", "--ignore-errors", "-a", str(listing), "-o", str(Path(tmp) / "%(id)s.%(ext)s")),
                capture_output=True, text=True, timeout=120 + 30 * len(urls),
            )
            stderr = got.stderr
            have = {f.name.split(".")[0] for f in Path(tmp).glob("*.vtt")}
            missing = [u for u, m in ids.items() if m and m.group(1) not in have]
            if not missing or "429" not in stderr or attempt:
                break
            listing.write_text("\n".join(missing) + "\n", encoding="utf-8")
            time.sleep(6)
        for url, match in ids.items():
            vtt = sorted(Path(tmp).glob(f"{match.group(1)}*.vtt")) if match else []
            if not vtt:
                limited = match and match.group(1) in stderr and "429" in stderr
                found[url] = {"moments": [], "reason": "rate limited by YouTube (HTTP 429)" if limited else "no English subtitles"}
                continue
            cues = parse_vtt(vtt[0].read_text(encoding="utf-8", errors="replace"))
            found[url] = {"moments": _score(cues, want, limit), "cues": len(cues)}
    return found


def spoken(url: str, words: str, limit: int = 3) -> dict[str, Any]:
    """Where in one video the words are said."""

    return spoken_many([url], words, limit)[url]
