# B-roll library

A decision chart is every way an interaction can go. Each box is a line. Each arrow is a decision. A path is one route from the first box to a last box. The chart comes from the request you bring. This app does not ship one.

Approved lines are footage for a later build. They are not the intent. The locked intent is the master cartouche in [INTENT.md](INTENT.md).

## Seek

`cartouche fetch spec.json` walks the chart and lists every box a path can reach. It does not create a clip. A box no path reaches is unreached and is not fetched.

## Fill

`cartouche fill spec.json -o clip_dictionary.json` puts one dictionary entry on the interaction shelf for each distinct line. A line that sits on two ordinary paths is still one entry. An edge case is not that line. It gets its own clip, even when the words are the same, and it is signed off on its own. Fill does not invent footage. It reserves a clip path and marks the entry `pending`.

Running fill again keeps what is already there. An approved line is not turned back into a pending one.

## Check-off

A pending line is not part of the build and is not reusable.

`cartouche view clip_dictionary.json --interaction <interaction> --phrase "<line>"` records the bytes that were seen. A missing file is not a viewing. An empty file is not a viewing.

`cartouche approve clip_dictionary.json --interaction <interaction> --phrase "<line>"` signs off that clip. If the file has changed since it was seen, the sign-off is refused.

That sets the entry to `approved` and writes its signal lock. The lock is the hash of the token, the phrase, and the primitive. A pending line has no lock. A path is covered only when every line on it is approved.

## Reuse

The next request can name the same interaction. Fill looks up each line by its normalized phrase on that shelf. An approved match comes back as `reused` and no second entry is written. A different wording is a different clip.
