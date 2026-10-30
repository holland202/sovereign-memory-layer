# How to test SML (and how to report)

Thanks for looking. The most useful thing you can do is **try to make it do something its documentation says it won't**, then tell me exactly how.

## 5-minute check

```bash
git clone https://github.com/holland202/sovereign-memory-layer
cd sovereign-memory-layer
sha256sum -c MANIFEST_HARDENED.sha256      # macOS: shasum -a 256 -c MANIFEST_HARDENED.sha256
python3 verify_hardened.py                 # expect "verdict": "PASS", exit 0
```

It needs Python 3.10 or newer, standard library only, on Linux or macOS. Windows is not supported, because the store uses POSIX file locking. Running it on Android/Termux would be especially useful; nobody has yet.

## What it promises (try to break these)

1. A save either completes fully or leaves the previous state, even if the process is killed.
2. A damaged or invalid data file is refused with `IntegrityError`. It is never loaded wrongly, and it never crashes with another error.
3. Protected records are never dropped. A save over the size limits is refused, and nothing changes.
4. Corrections and withdrawals keep the earlier record's history.
5. `recall()` answers UNKNOWN when evidence is missing or contradictory. It never gives one value while a different current value exists for that key.
6. IDs are exact positive integers. Keys are Unicode-normalized, and keys and source labels refuse control characters.
7. Several processes or threads saving at once don't lose or duplicate records.

## Already known (no need to report, unless it's worse than stated)

- A copied-back older data file is accepted (no rollback protection).
- No encryption, and no protection from someone who can write the folder.
- Not tested on real power loss.
- Retrieval is word-hashing, not semantic.
- The importance weighting has not been shown to beat "most recent first".

Full lists: `attack/RESULTS.md` and `review/round2_chatgpt/RESULTS_ROUND2.md`.

## Reporting

Open an issue using the **Test report** template. Passing runs are welcome too: "it worked on my machine" from a real person is evidence we don't have yet. Please include the exact commands and the full output. Failed tests and negative results get the same credit as passes.
