# SML: Sovereign Memory Layer

A small offline memory store for AI agents. Python standard library only.

## What it does

- It keeps facts with a timestamp and a source.
- You can correct or withdraw a fact without erasing what was there before.
- It has hard limits on record count and file size. A write that would break a limit is refused; protected records are never silently dropped.
- It survives being killed mid-write, and it refuses to open a damaged file.
- It answers **UNKNOWN** when its evidence is missing or contradicts itself.

## Run it

```bash
python3 verify_hardened.py      # 69 tests + 12 fix-removal mutants; exit 0 = pass
python3 -m unittest discover -s tests -v
python3 attack/attack.py --target .     # Claude's attack suite (A1-A15)
python3 attack/explore.py --target .    # exploratory attacks (E1-E5)
```

**Please try to break it.** See [TESTING.md](TESTING.md) for a five-minute check and how to report. Passes and failures are both useful.

## Status (honest)

- **Self-tested only.** Claude (Anthropic) and ChatGPT (OpenAI) built and attacked it at Chad Holland's direction. No person has independently tested it yet.
- **Not tested** on real power loss, a phone's filesystem, or hostile users.
- **Not shown** to retrieve better than "most recent first".

What broke and what was fixed: round 1 (Claude) in [`attack/RESULTS.md`](attack/RESULTS.md); round 2 (ChatGPT found, Claude fixed) in [`review/round2_chatgpt/RESULTS_ROUND2.md`](review/round2_chatgpt/RESULTS_ROUND2.md). Known limits are at the end of `attack/RESULTS.md`.

## History

This tree started as the October 29 identifier-fix candidate. It has had two hardening rounds: Claude found and fixed 6 defects, then ChatGPT found 6 more, which Claude fixed. See [PUBLICATION_NOTE.md](PUBLICATION_NOTE.md) for the one file removed before publishing. Its README is kept as `README_CANDIDATE.md`, its `MANIFEST.sha256` and `verify_candidate.py` are unchanged, and the original patch is under `originals/`. `MANIFEST_HARDENED.sha256` covers this version.

Provenance: Claude (Anthropic, Opus 5.5) attacked, fixed and tested this on 2026-10-30 → human validation: not performed → human editing/curation: none → responsibility: Chad Holland. Review level: direction only.
