"""FLY-002: storage that returns different bytes than were written. See PREREG.md, committed first.

FLY-001 truncated the file; that is invalid JSON, so the parser objected before the digest was ever
consulted, and deleting the checksum did not change the verdict. Here the damage keeps the JSON valid
and the schema intact, so the digest is the only thing that can object.

Run:  python3 review/fly002_2026-11-09/fly002.py [--sabotage]
Exit: 0 when every registered prediction holds; 1 otherwise. Under --sabotage, exit 0 means P1 failed
      as the registration requires."""
import json, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from sml.memory import MemoryStore, IntegrityError  # noqa: E402

SABOTAGE = "--sabotage" in sys.argv
PROV = {"source": "fly002", "locator": "PREREG.md", "sha256": "0" * 64}


def fresh():
    d = pathlib.Path(tempfile.mkdtemp(prefix="fly002_")) / "store"
    return MemoryStore(d, create=True)


def corrupt_one_value(path, old, new):
    """Change one stored value in place. JSON stays valid; the schema stays intact; the digest moves."""
    env = json.loads(path.read_text())
    hit = 0
    for rec in env["payload"]["records"]:
        if rec.get("value") == old:
            rec["value"] = new
            hit += 1
    assert hit == 1, f"expected exactly one record with value {old!r}, found {hit}"
    path.write_text(json.dumps(env))
    json.loads(path.read_text())            # the damage must leave parseable JSON
    return env["sha256"]


def load_store_class(sabotage):
    if not sabotage:
        return MemoryStore, IntegrityError
    import sml.memory as M
    src = pathlib.Path(M.__file__).read_text()
    marker = 'if env["sha256"] != digest(s):'
    assert src.count(marker) == 1, "checksum site moved; sabotage would be silent"
    ns = {}
    exec(compile(src.replace(marker, "if False:"), M.__file__, "exec"), ns)
    return ns["MemoryStore"], ns["IntegrityError"]


out, ok = [], True

# P0
st = fresh()
st.put("alpha", "one", provenance=PROV)
r = MemoryStore(st.directory, create=False).recall("alpha")
p0 = isinstance(r, dict) and r.get("status") == "KNOWN" and r.get("value") == "one"
out.append(("P0", "HELD" if p0 else "FAILED", f"honest commit -> status={r.get('status')!r} value={r.get('value')!r}"))
ok &= p0

# damage
st2 = fresh()
st2.put("alpha", "one", provenance=PROV)
st2.put("beta", "two", provenance=PROV)
corrupt_one_value(st2.path, "two", "twX")

Store, Integrity = load_store_class(SABOTAGE)

p1 = p2 = False
detail1 = detail2 = ""
try:
    s = Store(st2.directory, create=False)
    res = s.recall("beta")
    detail1 = f"no exception; recall('beta') status={res.get('status')!r} value={res.get('value')!r}"
    p2 = res.get("value") != "twX"
    detail2 = detail1
except Integrity as e:
    msg = str(e)
    p1 = "checksum mismatch" in msg
    detail1 = f"IntegrityError: {msg[:100]}"
    p2, detail2 = True, "no value returned"
except Exception as e:  # noqa: BLE001
    detail1 = f"wrong exception {type(e).__name__}: {str(e)[:80]}"
    p2, detail2 = True, "no value returned"

out.append(("P1", "HELD" if p1 else "FAILED", detail1))
out.append(("P2", "HELD" if p2 else "FAILED", detail2))

# P4 observation only
try:
    s4 = MemoryStore(st2.directory, create=False)
    s4.cleanup_incomplete()
    s4.put("gamma", "three", provenance=PROV)
    g = MemoryStore(st2.directory, create=False).recall("gamma")
    obs = f"recovered; later write readable -> {g.get('status')!r}"
except Exception as e:  # noqa: BLE001
    obs = f"not recovered: {type(e).__name__}: {str(e)[:70]}"

print(f"FLY-002 {'SABOTAGE RUN (checksum removed; P1 MUST fail)' if SABOTAGE else 'registered run'}")
for name, verdict, d in out:
    print(f"  {name}  {verdict:7} {d}")
print(f"  P4  OBSERVED {obs}")

if SABOTAGE:
    good = not p1
    print(f"VERDICT sabotage {'HELD (P1 failed as required)' if good else 'REFUTED (P1 still passed; FLY-002 is void)'}")
    sys.exit(0 if good else 1)
print(f"VERDICT {'3 of 3 registered predictions held' if ok and p1 and p2 else 'NOT as registered'}")
sys.exit(0 if (ok and p1 and p2) else 1)
