# SKR-001 results (2026-11-02)

## What could have gone wrong, first

- **Self-tested.** Claude registered, built, ran and judged this. It is not independent review. The commenter who proposed the test has not run it.
- **One machine, one filesystem.** An x86_64 container, Python 3.13.18. **NOT VALIDATED on the S25.** Android's `flock` and `fsync` were not exercised by this run.
- **A self-sent SIGKILL is a stand-in for an outside kill timer.** It lands exactly at the named stage, which is stronger targeting than a timer but is not a power cut, and it does not test filesystems that lie about fsync.
- **One change after registration, made before any run:** the harness's exit code. A draft exited 0 when sabotage was caught. The registration says the harness exits 1 under sabotage, so the committed harness exits 0 only when all six predictions hold. Nothing was retuned after seeing results.
- **The overlap measure is crude.** It counts lock waits longer than 1 ms. It shows that writers contended, not how often a kill landed while another writer was waiting.

## Raw output

`run.txt` has one JSON line per trial, then:
```
P1: HELD  (24/24 trials)
P2: HELD  (24/24 trials)
P3: HELD  (24/24 trials)
P4: HELD  (24/24 trials)
P5: HELD  (24/24 trials)
P6: HELD  (24/24 trials)
trials with a contended lock wait (>1 ms): 24/24
trials where the victim died by SIGKILL: 24/24
VERDICT 6 of 6 as registered
```
The sabotage run, `run_sabotage.txt`, with the file lock removed in the writers:
```
P1: REFUTED  (12/24 trials)
P2: REFUTED  (1/24 trials)
P3: REFUTED  (9/24 trials)
P4: REFUTED  (12/24 trials)
P5: REFUTED  (12/24 trials)
P6: REFUTED  (12/24 trials)
trials with a contended lock wait (>1 ms): 0/24
trials where the victim died by SIGKILL: 4/24
VERDICT 0 of 6 as registered (SABOTAGE RUN)
SABOTAGE CAUGHT
```
The counts in brackets are trials where the prediction held. Without the lock:
- 12 of 24 stores were left unreadable (`IntegrityError`);
- acknowledged writes were lost in 23 of 24 trials;
- most writers died with `FileNotFoundError` on the shared pending file before reaching their kill point.

## Predictions

| ID | Prediction | Result |
|---|---|---|
| P1 | the store opens after the kill | HELD, 24/24 |
| P2 | no acknowledged write is lost | HELD, 24/24 |
| P3 | nothing unacknowledged appears (at most 1 after the rename) | HELD, 24/24 |
| P4 | ids run 1..N with no gaps | HELD, 24/24 |
| P5 | a fresh writer gets id N + 1 | HELD, 24/24 |
| P6 | recall on the key returns UNKNOWN with exactly the current ids | HELD, 24/24 |
| Control | sabotage fails P1, P2 or P4 | CAUGHT (exit 1) |
| Rival | the writers rarely overlapped | Ruled out: contended lock waits in 24/24 trials, about 140 per trial |

## What this shows and does not show

- **Shows (implementation, this machine):** with 4 processes writing the same key and one killed at any of three commit points, the file lock and the write-then-rename commit kept every acknowledged write and showed no phantom writes. The store stayed usable. The control shows the harness detects exactly these failures when the lock is removed.
- **Does not show:**
  - behaviour on Android, on network filesystems, under power loss, or with a lying fsync;
  - more than 4 writers;
  - that "UNKNOWN on contradiction" is the right answer for a user. That is the separate benchmark, `review/unknown_vs_recency_2026-11-02/PREREG.md`.

## Open

- Run on the S25 with one command: `python3 review/skr001_2026-11-02/skr001.py`.
- Run with K = 8 writers.
- Credit the commenter by name once they agree.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland. SELF-TESTED.
