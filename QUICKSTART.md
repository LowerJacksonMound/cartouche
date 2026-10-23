# Cartouche in ten minutes

You sign off every line of a request, Cartouche locks the signed lines into one hash, and a Claude Code
build agent is judged against that hash while it writes. This walks the fixture request that ships in
`cartouche/tests/fixture/`: a phone call to book a car in, five lines, two paths (booked, or voicemail).

Every command below was run as written on 2026-10-23. The lines under each one are its real output, with
the working folder shortened to `$W`.

## You need

- a Mac
- Python 3.9 or newer as `python3` on your PATH. macOS ships 3.9.6 as `/usr/bin/python3`; nothing to install.
- Claude Code installed (`claude` on your PATH) for the MCP part

## Set up

`CT` is this folder. The CLI is `python3 -m cartouche`; the walkthrough runs in a scratch folder.

    export CT=/absolute/path/to/MCP-CARTOUCHE   # the folder this README is in
    export PYTHONPATH=$CT
    mkdir -p ~/ct-demo && cd ~/ct-demo
    cp $CT/cartouche/tests/fixture/domain_spec.json spec.json

## 1. Fetch: walk the chart

    python3 -m cartouche fetch spec.json

    sought=5 found=0 missing=5 undeclared=0 unreached=0

Five boxes are reachable. `missing=5` because no clip exists yet, at the path the spec declares
(`clips/tok_*.mp4`) or on the shelf (`library/phone_conversation/<digest>.mp4`, step 3); fetch lists, it
does not create a clip. The report is written beside the spec as `spec.fetch.json` (`-o` names another
path). It has each line, its primitive, and what it decides.

## 2. Fill: one shelf entry per line

    python3 -m cartouche fill spec.json -o clip_dictionary.json

    interaction=phone_conversation pending=5 approved=0 reused=0 paths=0/2

Each line is `pending` with a reserved clip path. Print them:

    python3 -c 'import json; d=json.load(open("clip_dictionary.json")); [print(e["status"], e["clip_path"], "|", e["phrase"]) for e in d["interactions"]["phone_conversation"].values()]'

    pending library/phone_conversation/9a43f021534930df.mp4 | Dick's Automotive, how can I help you?
    pending library/phone_conversation/3867dc78cbdb8ba1.mp4 | Yeah, this is Mike.
    pending library/phone_conversation/c117a34fe5682c06.mp4 | I need to book a Tuesday morning slot for a 1989 Lotus Esprit.
    pending library/phone_conversation/685f7501f3ba3d2e.mp4 | You're on the books for Tuesday at 9.
    pending library/phone_conversation/2ea35e08de310b7b.mp4 | Please leave a message after the tone.

Nothing can be approved yet. Try, and see the refusals:

    python3 -m cartouche approve clip_dictionary.json --interaction phone_conversation --phrase "Dick's Automotive, how can I help you?"

    approved=false reason=unseen
    (exit 2)

    python3 -m cartouche release spec.json clip_dictionary.json -o build_input.json

    released=false paths=0/2 files=false
    block: dick's automotive, how can i help you?
    block: i need to book a tuesday morning slot for a 1989 lotus esprit.
    block: please leave a message after the tone.
    block: yeah, this is mike.
    block: you're on the books for tuesday at 9.
    (exit 2)

An open path exits 2 and names the lines that block, one per line. The lock is not printed for a contract
that is not released; it is in `build_input.json`, with the same five lines under `blocks`.

## 3. Put the clips on the shelf

The clip is the footage you will look at. Put the bytes at the reserved path, relative to the folder you run
in (`--base`, default `.`). For the walkthrough, a few bytes per line stand in for a clip:

    python3 -c '
    import json, pathlib
    d = json.load(open("clip_dictionary.json"))
    for e in d["interactions"]["phone_conversation"].values():
        p = pathlib.Path(e["clip_path"]); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"clip bytes for: " + e["phrase"].encode())
    '

Fetch looks on the shelf too, so now it finds them:

    python3 -m cartouche fetch spec.json

    sought=5 found=5 missing=0 undeclared=0 unreached=0

## 4. View, then approve, each line

`view` records the bytes you saw. `approve` signs that viewing off and writes the signal lock.

    I=phone_conversation
    for ph in "Dick's Automotive, how can I help you?" "Yeah, this is Mike." "I need to book a Tuesday morning slot for a 1989 Lotus Esprit." "You're on the books for Tuesday at 9."; do
      python3 -m cartouche view    clip_dictionary.json --interaction $I --phrase "$ph"
      python3 -m cartouche approve clip_dictionary.json --interaction $I --phrase "$ph"
    done

    seen=true
    approved dick's automotive, how can i help you?
    seen=true
    approved yeah, this is mike.
    seen=true
    approved i need to book a tuesday morning slot for a 1989 lotus esprit.
    seen=true
    approved you're on the books for tuesday at 9.

The fifth line is the voicemail edge case. View it, then change the file, then try to approve:

    python3 -m cartouche view clip_dictionary.json --interaction $I --phrase "Please leave a message after the tone."
    printf 'different bytes' > library/phone_conversation/2ea35e08de310b7b.mp4
    python3 -m cartouche approve clip_dictionary.json --interaction $I --phrase "Please leave a message after the tone."

    seen=true
    approved=false reason=replaced
    (exit 2)

The bytes changed, so the sign-off is not that clip. View the new bytes and approve:

    python3 -m cartouche view    clip_dictionary.json --interaction $I --phrase "Please leave a message after the tone."
    python3 -m cartouche approve clip_dictionary.json --interaction $I --phrase "Please leave a message after the tone."

    seen=true
    approved please leave a message after the tone.

## 5. Release: lock the intent

    python3 -m cartouche release spec.json clip_dictionary.json -o build_input.json

    released=true paths=2/2 files=true
    cd093843aefe1778ba3e8a43c951fb3fc2531ca7ff8632898c3d278acaf0c6f5
    (exit 0)

Both paths are covered. `build_input.json` is the release: the contract's clips are the build input, and
`cartouche_sha256` is the master cartouche. It is the hash the build is judged against from here on.

Two more things to see once, both optional:

    python3 -m cartouche fill spec.json -o clip_dictionary.json
    interaction=phone_conversation pending=0 approved=5 reused=0 paths=2/2

A second fill finds the lines signed off for this request as `approved` and writes nothing new. A later
request on the same interaction finds them too, as `reused`: the entry pre-existed, signed off under an
earlier request. The released contract carries the same word per clip.

    python3 -m cartouche resolve spec.json clip_dictionary.json --phrase "Yeah, this is Mike."
    resolved=true reason=signal
    07f643d814efd566

That is the signal lock for one line. Before approval the same text answers `unsigned`.

## 6. Register the MCP server with Claude Code

Once, from this folder:

    bash $CT/install_cartouche_mcp.sh --print     # show the command, change nothing
    bash $CT/install_cartouche_mcp.sh             # register at user scope

`--print` shows:

    claude mcp add-json --scope user cartouche '{"type":"stdio","command":"$CT/cartouche-mcp.sh","args":[]}'

The server starts with no target. `ct_watch` names it. Nothing is written into any repo.

## 7. From a Claude Code session: watch, look, stop

Put a build where the agent will write it. For the walkthrough, copy the sealed fixture agent in as the
"finished" build:

    mkdir -p build && cp $CT/cartouche/tests/fixture/agent_sealed.py build/agent.py

Open Claude Code anywhere and tell it to call the three tools with absolute paths. The same calls, made
over stdio to `cartouche-mcp.sh`, answered as follows.

`ct_look` before any watch:

    {"error": "no target — call ct_watch with the spec, the release, and the build path"}

`ct_watch(spec="$W/spec.json", contract="$W/build_input.json", target="$W/build")`:

    {"sealed": true, "waiting": false, "scanned": true, "reason": "scan",
     "cartouche_sha256": "cd093843aefe1778ba3e8a43c951fb3fc2531ca7ff8632898c3d278acaf0c6f5",
     "projection_residual": 0.0, "target": "$W/build", "open": 0, "issues": [], "bound": true}

`ct_look()` after the agent writes:

    {"sealed": true, ..., "projection_residual": 0.0, "open": 0, "issues": [], "bound": true}

`ct_stop()` when the build is finished:

    {"sealed": true, ..., "open": 0, "issues": [], "bound": false, "stopped": true}

Now a build that drifted. The fixture `agent_shifted_edge.py` has the same bodies minus the call from
`verify_human` to `transmit_request`:

    mkdir -p shifted && cp $CT/cartouche/tests/fixture/agent_shifted_edge.py shifted/agent.py

`ct_watch(..., target="$W/shifted")` then `ct_look()`:

    {"sealed": false, "projection_residual": 1.0, "target": "$W/shifted", "open": 1,
     "issues": [{"file": "$W/shifted/agent.py", "function": "fxnB_verify_human", "lines": [13, 13],
                 "fault": "skew",
                 "detail": "TOPOLOGY_BREAK(fxnB_verify_human->fxnC_transmit_request)",
                 "directive": "Topological invariant violation: 'fxnB_verify_human' must transition to or be sequenced with 'fxnC_transmit_request'."}],
     "bound": true}

`fault` is one of the five defect words from INTENT.md: `template` (a hollow stub), `locked` (the request
was edited after release), `hazy` (the function is there but not clear: a constant return, too thin),
`missing` (the function is not there), `skew` (a required edge is gone). A file that does not parse is
`SYNTAX`. `detail` keeps the scanner's own codes. Give that row to the build agent. Cartouche keeps
watching; it does not fix the file. A `ct_watch` on a different target while this one is bound answers:

    {"error": "ct_stop first — a build is already being watched"}

`ct_stop()`:

    {"sealed": false, "open": 1, "issues": [ ...the same row... ], "bound": false, "stopped": true}

Two more answers worth knowing. A release that is not signed off (the `build_input.json` from step 2,
before approval) is refused at `ct_watch`:

    {"error": "the request is not signed off, so nothing is being watched"}

A target the agent has not written yet is not a miss:

    {"sealed": false, "waiting": true, "scanned": false, "reason": "waiting", "target": "$W/later.py",
     "open": 0, "issues": [], "bound": true}

## What `sealed` means

`sealed: true` from `ct_stop` means the tree is the locked intent: residual `0.00`, every required edge
present, every primitive there and not hollow, under the same `cartouche_sha256` that `release` printed.
`sealed: false` means at least one issue is open, and it is listed. Nothing on the Cartouche side changed
either way: the release file is not rewritten, and the lock does not move to meet the code.

The same comparison from a terminal, once, with no watch:

    python3 -m cartouche hold spec.json build_input.json build/agent.py -o hold.json
    held=true sealed=true residual=0.00 warrants=0

    python3 -m cartouche hold spec.json build_input.json shifted/agent.py -o hold2.json
    held=true sealed=false residual=1.00 warrants=1
    issue: fault=skew function=fxnB_verify_human file=shifted/agent.py lines=13-13 detail=TOPOLOGY_BREAK(fxnB_verify_human->fxnC_transmit_request)
    (exit 2)

`cartouche start` prints the same `issue:` lines while it watches, and `hold.json` carries them as `issues`.

## Self-test

    cartouche selftest
    sh plants/run_all.sh

The rules behind each answer are in INTENT.md, MCP.md and BROLL.md.
