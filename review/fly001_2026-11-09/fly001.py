"""FLY-001: a filesystem that lies about fsync. See PREREG.md, committed before this harness existed.

The lie: os.fsync is a no-op. At `after_file_fsync` - the instant _commit believes the payload is
durable - the pending file is truncated to a prefix, modelling the tail that never reached storage.
The commit then proceeds as written: os.replace runs, the rename survives, the file it names is short.

The question is not whether data is lost. It is whether SML fails closed on the torn snapshot."""
import os, sys, pathlib, tempfile, traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from sml.memory import MemoryStore, IntegrityError  # noqa: E402

SABOTAGE = "--sabotage" in sys.argv
PROV = {"source": "fly001", "locator": "PREREG.md",
        "sha256": "0" * 64}


def new_store(fault=None):
    d = pathlib.Path(tempfile.mkdtemp(prefix="fly001_")) / "store"
    return MemoryStore(d, create=True, fault=fault)


def put(st, key, value):
    return st.put(key, value, provenance=PROV)


def reopen(d):
    return MemoryStore(d, create=False)


results = {}

# P0 anti-vacuity: honest fsync, no truncation, same code path
st = new_store()
put(st, "alpha", "one")
got = reopen(st.directory).recall("alpha")
results["P0"] = ("HELD" if got is not None else "FAILED", f"recall after honest commit -> {got!r}")

# The lie
real_fsync = os.fsync
os.fsync = lambda fd: None

st2 = new_store()
put(st2, "alpha", "one")                      # one good commit before the lie bites
pending = st2.pending


def liar(stage):
    if stage == "after_file_fsync" and pending.exists():
        raw = pending.read_bytes()
        pending.write_bytes(raw[: max(1, len(raw) // 3)])   # the tail never landed


st2.fault = liar
try:
    put(st2, "beta", "two")
except Exception as e:                                     # a raise here is acceptable
    results["_commit_raised"] = f"{type(e).__name__}: {e}"

if SABOTAGE:  # P4: remove the checksum check that P2 depends on
    import sml.memory as M
    src = pathlib.Path(M.__file__).read_text()
    assert 'if env["sha256"] != digest(s):' in src
    ns = {}
    exec(compile(src.replace('if env["sha256"] != digest(s):', "if False:"), M.__file__, "exec"), ns)
    Store = ns["MemoryStore"]
    Integrity = ns["IntegrityError"]
else:
    Store, Integrity = MemoryStore, IntegrityError

# P1/P2: what does a reader do with the torn snapshot?
verdict, detail = "FAILED", ""
try:
    s3 = Store(st2.directory, create=False)
    val = s3.recall("beta")
    old = s3.recall("alpha")
    verdict = "FAILED"
    detail = f"no exception; recall('beta')={val!r} recall('alpha')={old!r}"
except Integrity as e:
    verdict, detail = "HELD", f"IntegrityError: {str(e)[:90]}"
except Exception as e:
    verdict, detail = "FAILED", f"wrong exception {type(e).__name__}: {str(e)[:80]}"
results["P1/P2"] = (verdict, detail)

os.fsync = real_fsync

# P3: is the store usable afterwards?
try:
    s4 = MemoryStore(st2.directory, create=False)
    s4.cleanup_incomplete()
    put(s4, "gamma", "three")
    ok = MemoryStore(st2.directory, create=False).recall("gamma")
    results["P3"] = ("HELD" if ok is not None else "FAILED", f"write+recall after the tear -> {ok!r}")
except Exception as e:
    results["P3"] = ("FAILED", f"{type(e).__name__}: {str(e)[:100]}")

print(f"FLY-001 {'SABOTAGE RUN (checksum removed; P2 MUST fail)' if SABOTAGE else 'registered run'}")
for k, v in results.items():
    if isinstance(v, tuple):
        print(f"  {k:8} {v[0]:7} {v[1]}")
    else:
        print(f"  {k:8} {' ':7} {v}")
