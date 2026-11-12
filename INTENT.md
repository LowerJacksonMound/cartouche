# Intent signal

The intent is the master cartouche. It is locked before an author agent writes, and it stays the same lock for the whole build. Clip approval is not the intent. CLOSER and CodeRadar do not mint a new one.

## What is locked

One signal per primitive:

```text
sha256(f"{token_id}::{phrase.strip().lower()}::{primitive_fxn}")[:16]
```

The stitcher puts those hashes on the certified signal track, with the required edges and the glyph slots. The compiler folds that track into the master cartouche:

- `domain_id`
- one sub-glyph per primitive: slot, bit, signal hash, region, polygon, invariants
- `required_edges`, sorted

`cartouche_sha256` is the sha256 of that payload with sorted keys. The same track always yields the same hash. A different phrase, token, function name, slot, edge, or invariant is a different intent.

The lock is the hash of the signed signals. Approving a line does not move it.

The scanner is a lock on names, parameters and order; behaviour is Closer's claims. Order is read from the call graph, and from two things the call graph does not show: a module-level dispatch table a function reads, and a loop that drives the order from what it hears. A heard edge whose two ends one loop-owning function reaches is satisfied (ruling 2026-11-03, the counter).

## What the lock is for

Cartouche holds this lock from the request through the final tree. A scan compares an author agent's code to it. Residual `0.00` and a full bitmask means the tree is the locked intent. Anything else is an expectation miss. Cartouche reports that. It does not rewrite the lock to match the code.

## The other two apps

They stay standalone. Cartouche does not call them. They are the running environment this lock is meant to sit in.

| App | Where | When it runs | What it owns |
|---|---|---|---|
| Cartouche | this build | the entire build | the intent lock, and whether the tree still matches it |
| CLOSER_THE_APP | Drive folder `CLOSER_THE_APP` | while an author agent is generating | counterfeit code before it is written |
| CodeRadar | Drive folder `NEW_CODE_RADAR_REFURBISH` | the entire build, last position | counterfeit code that reached a file, and its other file-side passes |

CLOSER is the pre-write gate (`getting-close`). It stops stubs, constant returns, swallowed exceptions, and hollow tests from landing. It does not decide whether landed code is what the user asked for. That comparison is the cartouche.

CodeRadar sits after the write. What CLOSER did not stop, CodeRadar detects and fixes on disk. It is not CLOSER, and the two do not talk.

The order in a build is not three phases that replace each other. The lock is up the whole time. CLOSER is up whenever code is being generated. CodeRadar is up on the files, in the last position. The final tree is what was asked for only when the same `cartouche_sha256` still seals.

## Release

`cartouche release spec.json clip_dictionary.json -o build_input.json` reads the shelf. It does not approve a line, invent a file, or render a montage.

Every path has to be covered. An open path exits 2 and names the lines that block. A covered shelf exits 0. The contract's clips are the build input, and no other lines are. `cartouche_sha256` in that contract is the same lock as the scan. This command does not call CLOSER or CodeRadar.

## Start and stop

You start Cartouche after the request is signed and released. It stays up until you stop it. CLOSER and CodeRadar are started and stopped by you. Cartouche does not start them, and it does not talk to them.

`cartouche start spec.json build_input.json target.py --session session.json` watches the build. When something does not match what you signed, it prints the issue and keeps watching. You give that issue to the build agent. Cartouche does not send it. A file that has not been written yet is not a failure and does not stop the watch.

`cartouche stop session.json` ends the watch. Stop when the build is finished. If it still does not match, stop exits 2. The release is not rewritten.

## MCP

The build agent uses the stdio server, not the printed sign line.

`python -m cartouche.mcp` from the `CARTOUCHE` folder, or `sh cartouche-mcp.sh`. No port. The server does not start CLOSER or CodeRadar.

| Tool | What it does |
|---|---|
| `ct_watch` | Bind the spec, the release, and the file or directory. An unsigned release is refused. Neither file is written. |
| `ct_look` | One scan. Each issue names the file, the function, the lines, and the fault. A directory is one scan. A file that does not parse is reported, and the watch stays up. Nothing written yet is waiting, not an issue. |
| `ct_stop` | End the watch and report any open issue. The release is not rewritten. The server process stays up. |
| `ct_hold` | The same comparison, once, without a watch. |

The CLI start and stop above are unchanged. A directory watched from the CLI is still judged file by file. The MCP watch is the one that treats the tree as one scan.

## Hold

`cartouche hold spec.json build_input.json target.py -o hold.json` is the only place a release and a scan meet.

An unreleased contract is not scanned. A spec that no longer hashes to the contract is not scanned. A scan that fails stays in `hold.json`. Hold does not rewrite the contract, the shelf, or the spec, and it does not call CLOSER or CodeRadar.

## Sequence

A cartouche holds at most `cartouche_capacity` symbols. The capacity is part of the request, not a fixed chart.

`cartouche sequence spec.json target.py -o sequence.json` checks that file against the pack. Order held means the symbols that exist are in that order, and a later cartouche is not sealed while an earlier one is open. Complete means every cartouche is sealed. The command does not change `cartouche_sha256`.

## Macro

`cartouche admit sequence.json -o cartouches.json` stores a complete sequence under its lock. An open sequence is not stored.

`cartouche compose image.json cartouches.json -o composition.json` places admitted locks in order, up to the image capacity. A lock that was never admitted is an open symbol. Compose does not invent it, and it does not rewrite the shelf. The image hash is the ordered locks. It is not the cartouche hash.

## Request

A request's values live in its phrases. They are not a second hash.

`cartouche instantiate spec.json request.json -o binding.json` holds only when every certified value matches. A different value or an unknown field exits 2. The spec is not rewritten.

## Phrase

Ambiguity comes off when the clip is signed off. That sign-off reduces the clip to one signal lock, stored on the dictionary entry. The build uses that lock. A later app reuses the entry.

`cartouche resolve spec.json clip_dictionary.json --phrase "..."` returns the lock only after that line is approved. The same text before sign-off is `unsigned`. A near line is `off_script` and is not rounded onto a lock. Resolve does not rewrite the shelf.

## Cartouche

`cartouche lock spec.json clip_dictionary.json -o master_cartouche.json` compiles the cartouche from signed-off signal locks. A line without a lock is not a symbol, and no cartouche file is written.

## Signs

The eye is one sign, not the dictionary. A part with one signal lock takes a one-function sign. Two locks take a two-function sign. Three take a three-function sign. The sign is the digest of those locks, modulo the signs that hold that many. The same locks always return the same sign. Each sign has a name, such as the eye or the falcon. The name is how you refer to that drawing. It is not what the function means. `cartouche mark` does this only after the shelf is locked, and it does not search for clips.

## Image

`cartouche image spec.json clip_dictionary.json -o image.json` draws one ring per part. The seal is that part's sign. The signs inside are the functions, in order. The drawing does not name them. An open shelf writes no image.

The scan has three defects: locked, missing, and skew. They apply to whichever sign is selected. A sign is sealed or it is not: there is no in-between grade. A check that cannot tell is let through, never a fault. A hollow or fake-shaped body and wrong parameters are CLOSER's to refuse; Cartouche reports missing, skew and locked. (Owner ruling 2026-11-11, one owner per fault kind: template and missing parameters moved to CLOSER, whose judge runs the function on the locked checks. Ruling 2026-10-24: hazy is retired; a short body alone is let through.) No sample request is loaded.

When the projection has a defect, the monitor says so and marks the tab. If you allow notifications, it also sends one. A clean projection does not. The same defect is not sent twice.

A clip is signed off only after its bytes have been seen. An empty file is not a viewing. If those bytes change, the sign-off is no longer that clip. Each signal in a cartouche gets its own sign. The desk does not show the lock. The code watch can be opened without signing the clips, and opening it does not sign them.














