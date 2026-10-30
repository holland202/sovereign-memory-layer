# Publication note (2026-10-30)

This history was written privately and published on 2026-10-30. Before publishing, **one file was removed from every commit**: `originals/SML_REVIEW_2026-10-29.zip`. That is the October 29 owner-review archive, sha256 `a735dd755537019b76e0a8afb70b89ab5beef33b241023af95ad305a8f8bfefa`. It contains historical source notes that are not being published. Nothing else was changed. The commit order is the original one, so the attack plan (`1d4d734`) still comes before any attack ran or any fix was made.

Because of the removal:
- the earlier `MANIFEST.sha256` lists a file that is not here;
- `verify_candidate.py`, which also pins an earlier source hash, will not pass.

Use `MANIFEST_HARDENED.sha256` and `verify_hardened.py` for this version.
