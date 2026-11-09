# FLY-001 — a filesystem that lies about fsync. Registration

**Status:** REGISTRATION, written before the harness exists. **Date:** 2026-11-09.
**Base:** `1eef4a0`. **Origin:** the fourth of Shivashish Jaishy's four proposed tests, and the only
one not yet run. SKR-001's own limits section says it "does not test filesystems that lie about
fsync". **Self-tested; the commenter who proposed it has not run it.**

## What is being tested

`_commit` writes the snapshot to `pending`, flushes, calls `os.fsync` twice, `os.replace`s it over
`path`, then fsyncs the directory. That sequence is correct **only if fsync means what it says.**
Some filesystems, and some Android-backed storage, acknowledge fsync without the data being durable.

When fsync lies and power is lost, the rename can survive while the bytes it points at do not. The
store then holds a snapshot that was never fully written, and which the code believes was confirmed
durable.

**The interesting question is not whether data is lost.** No software survives a lying fsync; a
write that was acknowledged can be gone. The question is whether SML then **fails closed** — refuses
the torn snapshot — or parses it and answers from it.

## Model of the lie

`os.fsync` is replaced with a no-op, which is the lie. At the `after_file_fsync` fault point — the
instant the code believes the payload is durable — the pending file is truncated to a prefix,
modelling the tail that never reached the platter. The commit then proceeds exactly as written:
`os.replace` runs, the rename survives, and the file it names is short.

This is a model, not a power cut. It reproduces the *ordering* a lying fsync permits. It does not
reproduce controller-level reordering, partially written sectors, or a filesystem that loses the
rename as well.

## Predictions

- **P0 (anti-vacuity).** With fsync honest and no truncation, a commit through the same code path
  leaves a readable store with the new value. If this fails the harness is broken, not SML.
- **P1.** After the lying-fsync truncation, recall **does not** return a value that was never
  committed, and does not return the truncated payload as if it were whole.
- **P2.** The torn snapshot is detected and surfaced as `IntegrityError`, not a parse of partial
  data. Any other exception type, or a silent success, refutes P2.
- **P3.** The store is still usable afterwards: a subsequent write succeeds and is readable.
- **P4 (sabotage).** With the sha256 check in `_decode` neutered, P2 must FAIL. If P2 still passes
  with the checksum removed, the test is not detecting what it claims and FLY-001 is void.

## Refutation criteria

P4 passing voids the experiment. P2 failing is a real finding and is kept, not retried with a
different truncation until it passes.

## Not covered

Real power loss. Filesystems that also lose the rename. Android's actual storage stack — this runs
in a container unless and until it is run on the S25. Rust implementation untouched.

## AI provenance

Registered by Claude (Anthropic) on owner direction, 2026-11-09, before the harness was written.
Proposed originally by Shivashish Jaishy. Not independently reviewed.
