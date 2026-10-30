# Attack brief for ChatGPT: break SML (round 2)

You are the second attacker. Claude (Anthropic) attacked this code first, fixed what it found, and wrote down what it did. **Your job is to find what Claude missed.** Agreeing with Claude is worth nothing; a reproducible failure is worth a lot.

## Setup

1. Unzip `SML_HARDENED_ROUND1.zip` into a fresh folder.
2. Check the files: `sha256sum -c MANIFEST_HARDENED.sha256`. Every line must say OK. If any doesn't, stop and report it.
3. Run `python3 verify_hardened.py`. It must exit 0 with 60 tests. Record your Python version and OS.

## What the store promises (attack these)

1. A write is all or nothing. A crash at any point leaves either the old state or the new one, and every acknowledged write survives.
2. A damaged or invalid file is refused with `IntegrityError`. It never loads wrong data and never crashes with some other exception.
3. Protected records are never silently dropped. A write that exceeds the record or byte limit is refused, and nothing changes.
4. A correction or revocation keeps the history: the old record stays and is marked superseded or revoked.
5. `recall()` returns UNKNOWN when the evidence is missing or contradictory. It never returns a value while a different current value exists for the same key.
6. Record IDs must be exact positive integers. Keys are NFC-normalized, and keys and provenance refuse control and format characters.
7. Several processes or threads can write at once without losing or duplicating records (local POSIX filesystem, cooperative writers).

## Already found and fixed (don't re-report; do check the fixes hold)

Deep-nesting crash, clock skew blocking revocation, clock skew hiding a contradiction, NFC/NFD duplicate keys, control and bidi characters in keys, and a lock path that is a directory. Details and raw outputs are in `attack/RESULTS.md`.

## Known limits (out of scope unless you find something worse than stated)

- Rollback to an older valid file is accepted.
- No encryption, and no protection against someone who can write the folder.
- No real power-loss test.
- Retrieval is lexical, not semantic.
- The importance weighting has not been shown to help.

## Suggested avenues Claude did NOT try

- Calling the store from within `clock()` or `fault()` callbacks (re-entrancy).
- `compact()` interleaved with corrections across processes.
- Very large inputs (10–16 MB values or many records) and speed.
- Symlinks and hard links inside the store folder.
- `umask` and permission edge cases.
- `OrthoProjection` with near-orthonormal bases.
- `retrieve()` argument edge cases (`half_life`, `top_k`, `threshold` at their bounds).
- Python 3.10 and 3.14.
- Termux/Android.
- Any way to make `recall()` say KNOWN wrongly.

## Rules

- Use synthetic data only.
- **Don't change the code you are attacking.** Write each attack as a separate script or test that fails on the current code. If you propose a fix, put it in a separate patch file.
- For every finding, report:
  - the exact command;
  - the full output;
  - what was expected;
  - what happened;
  - severity: wrong KNOWN, data loss, crash, or cosmetic.
- If you find nothing in an area, say what you tried. "No issues found" with no list of attempts doesn't count.
- Label your work as AI-generated (ChatGPT). Don't claim independent or human review.

## Return

Send back:
- one `CHATGPT_ATTACK_FINDINGS.md`;
- a folder of your attack scripts;
- their raw outputs.

Claude will then reproduce each finding, fix the real ones with a test per fix, and keep any it can't reproduce on record as UNKNOWN.
