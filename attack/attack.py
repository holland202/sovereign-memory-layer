#!/usr/bin/env python3
"""SML-ATK-001 attack harness (see ATTACK_PLAN.md). Synthetic inputs only.

Usage: python3 attack/attack.py --target DIR [--only A1,A2] [--json OUT]
DIR is a folder that contains the `sml` package (this repo's root, or a mutant copy).
Each attack prints one line: ID, OBSERVED outcome class, and evidence. The harness
reports what happened; ATTACK_PLAN.md says what was predicted.
"""
import argparse
import hashlib
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

P = {"source": "synthetic-atk", "locator": "atk-1", "sha256": hashlib.sha256(b"atk").hexdigest()}
RESULTS = {}


def load_target(target):
    sys.path.insert(0, str(target))
    import sml.memory as M  # noqa: E402
    from sml import policies  # noqa: E402
    return M, policies


def record(aid, outcome, **evidence):
    RESULTS[aid] = {"outcome": outcome, **evidence}
    print(f"{aid}: {outcome} {json.dumps(evidence, default=str)[:600]}", flush=True)


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def fresh(M, td, **kw):
    clock = kw.pop("clock", Clock())
    return M.MemoryStore(Path(td) / "s", create=True, clock=clock, **kw), clock


def classify_load(M, path):
    """Open an existing store. Returns ('integrity'|'ok'|'other:<Exc>', snapshot-or-None)."""
    try:
        m = M.MemoryStore(path)
        return "ok", m.snapshot()
    except M.IntegrityError:
        return "integrity", None
    except BaseException as e:  # noqa: BLE001 - we want to see everything that escapes
        return f"other:{type(e).__name__}", None


# ---------------------------------------------------------------- A1-A4: on-disk corruption

def build_valid(M, td, n=6):
    m, c = fresh(M, td)
    for i in range(n):
        c.t += 1
        m.put(f"k{i % 3}", f"value-{i}", provenance=P, protected=(i == 0))
    m.revoke(2, reason="r", provenance=P)
    c.t += 1
    m.correct(3, "fixed", provenance=P)
    return m


def a1(M):
    with tempfile.TemporaryDirectory() as td:
        m = build_valid(M, td)
        depth = 100_000
        m.path.write_bytes(b"[" * depth + b"]" * depth)
        cls, _ = classify_load(M, m.path.parent)
        record("A1", "integrity_error" if cls == "integrity" else cls, depth=depth, bytes=2 * depth)


def a2(M, n=3000, seed=20261030):
    rng = random.Random(seed)
    counts = {"integrity": 0, "identical": 0, "accepted_different": 0}
    others = {}
    with tempfile.TemporaryDirectory() as td:
        m = build_valid(M, td)
        good = m.path.read_bytes()
        orig = json.loads(good)["payload"]
        for _ in range(n):
            b = bytearray(good)
            i = rng.randrange(len(b))
            b[i] = (b[i] + rng.randrange(1, 256)) % 256
            m.path.write_bytes(bytes(b))
            cls, snap = classify_load(M, m.path.parent)
            if cls == "integrity":
                counts["integrity"] += 1
            elif cls == "ok":
                counts["identical" if snap == orig else "accepted_different"] += 1
            else:
                others[cls] = others.get(cls, 0) + 1
        m.path.write_bytes(good)
    bad = counts["accepted_different"] + sum(others.values())
    record("A2", "clean" if not bad else "defect", flips=n, **counts, other_exceptions=others)


def a3(M, n=400, seed=7):
    rng = random.Random(seed)
    res = {}
    with tempfile.TemporaryDirectory() as td:
        m = build_valid(M, td)
        good = m.path.read_bytes()
        cuts = sorted({0, len(good) - 1, *(rng.randrange(len(good)) for _ in range(n))})
        for cut in cuts:
            m.path.write_bytes(good[:cut])
            cls, _ = classify_load(M, m.path.parent)
            res[cls] = res.get(cls, 0) + 1
        m.path.write_bytes(good)
    record("A3", "clean" if set(res) == {"integrity"} else "defect", cuts=len(cuts), outcomes=res)


def a4(M):
    out = {}
    with tempfile.TemporaryDirectory() as td:
        m = build_valid(M, td)
        good = m.path.read_bytes()
        env = json.loads(good)
        payload = env["payload"]

        def env_for(p):
            return M.canonical({"payload": p, "sha256": M.digest(p)}) + b"\n"
        cases = {
            "empty_file": b"",
            "invalid_utf8": b"\xff\xfe" + good,
            "duplicate_key": good.replace(b'{"payload":', b'{"payload":1,"payload":', 1),
            "nan_literal": good.replace(b'"generation":', b'"generation":NaN,"x":', 1),
            "huge_int": good.replace(b'"generation":', b'"generation":' + b"9" * 5000 + b',"y":', 1),
            "missing_envelope": M.canonical(payload),
            "extra_envelope_field": M.canonical({**env, "extra": 1}),
        }
        p = json.loads(json.dumps(payload))
        p["records"][0]["weight"] = "1"
        cases["wrong_type_with_valid_checksum"] = env_for(p)
        p = json.loads(json.dumps(payload))
        p["records"][0]["extra"] = 1
        cases["extra_record_field_valid_checksum"] = env_for(p)
        p = json.loads(json.dumps(payload))
        p["records"][0]["id"] = True
        cases["bool_id_valid_checksum"] = env_for(p)
        for name, data in cases.items():
            m.path.write_bytes(data)
            out[name] = classify_load(M, m.path.parent)[0]
        m.path.write_bytes(good)
    record("A4", "clean" if set(out.values()) == {"integrity"} else "defect", cases=out)


# ---------------------------------------------------------------- A5-A6: processes

CHILD = r'''
import os, sys, json, itertools
sys.path.insert(0, sys.argv[1])
from sml.memory import MemoryStore
P = json.loads(sys.argv[4])
m = MemoryStore(sys.argv[2])
ack = open(sys.argv[3], "a")
for i in itertools.count():
    key = f"w{os.getpid()}.{i}"
    m.put(key, "v", provenance=P)
    ack.write(key + "\n"); ack.flush(); os.fsync(ack.fileno())
'''


def a5(M, target, trials=150, seed=11):
    rng = random.Random(seed)
    problems = []
    stats = {"trials": trials, "reopened_ok": 0, "acked_total": 0, "unacked_extra_total": 0, "pending_left": 0}
    for t in range(trials):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "s"
            M.MemoryStore(store, create=True, max_records=100000, max_bytes=16_000_000)
            ack = Path(td) / "ack"
            ack.touch()
            proc = subprocess.Popen([sys.executable, "-c", CHILD, str(target), str(store), str(ack), json.dumps(P)],
                                    stderr=subprocess.PIPE)
            time.sleep(rng.uniform(0.15, 0.6))
            proc.send_signal(signal.SIGKILL)
            proc.wait()
            acked = [x for x in ack.read_text().split("\n") if x]
            cls, snap = classify_load(M, store)
            if cls != "ok":
                problems.append({"trial": t, "reopen": cls})
                continue
            stats["reopened_ok"] += 1
            keys = [r["key"] for r in snap["records"]]
            ids = [r["id"] for r in snap["records"]]
            missing = set(acked) - set(keys)
            extra = set(keys) - set(acked)
            stats["acked_total"] += len(acked)
            stats["unacked_extra_total"] += len(extra)
            stats["pending_left"] += (store / "memory.pending").exists()
            if missing or len(extra) > 1 or len(set(ids)) != len(ids):
                problems.append({"trial": t, "missing": sorted(missing)[:3], "extra": len(extra)})
    record("A5", "clean" if not problems else "defect", **stats, problems=problems[:5])


CONC = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
from sml.memory import MemoryStore
P = json.loads(sys.argv[4])
m = MemoryStore(sys.argv[2])
for i in range(int(sys.argv[5])):
    m.put(f"p{sys.argv[3]}.{i}", "v", provenance=P)
'''


def a6(M, target, procs=8, each=40, rounds=3):
    problems = []
    for rnd in range(rounds):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "s"
            M.MemoryStore(store, create=True, max_records=100000, max_bytes=16_000_000)
            ps = [subprocess.Popen([sys.executable, "-c", CONC, str(target), str(store), str(k), json.dumps(P), str(each)],
                                   stderr=subprocess.PIPE) for k in range(procs)]
            errs = [p.communicate()[1].decode()[-200:] for p in ps]
            codes = [p.returncode for p in ps]
            cls, snap = classify_load(M, store)
            if cls != "ok":
                problems.append({"round": rnd, "reopen": cls, "codes": codes})
                continue
            ids = [r["id"] for r in snap["records"]]
            keys = {r["key"] for r in snap["records"]}
            if len(ids) != procs * each or sorted(ids) != list(range(1, procs * each + 1)) or len(keys) != procs * each \
                    or any(codes):
                problems.append({"round": rnd, "records": len(ids), "unique_keys": len(keys), "codes": codes,
                                 "stderr": [e for e in errs if e][:1]})
    record("A6", "clean" if not problems else "defect", procs=procs, each=each, rounds=rounds, problems=problems)


# ---------------------------------------------------------------- A7-A8: clock skew

def a7(M):
    out = {}
    with tempfile.TemporaryDirectory() as td:
        m, c = fresh(M, td)
        i = m.put("k", "v", provenance=P)
        c.t = 500.0  # clock moved backwards
        for op in ("revoke", "correct"):
            before = m.path.read_bytes()
            try:
                if op == "revoke":
                    m.revoke(i, reason="withdraw", provenance=P)
                else:
                    m.correct(i, "v2", provenance=P)
                out[op] = "allowed"
            except Exception as e:  # noqa: BLE001
                out[op] = f"refused:{type(e).__name__}:{e}"
            out[op + "_unchanged"] = m.path.read_bytes() == before
    refused = any(str(v).startswith("refused") for k, v in out.items() if not k.endswith("unchanged"))
    record("A7", "defect_withdrawal_blocked" if refused else "clean", **out)


def a8(M):
    with tempfile.TemporaryDirectory() as td:
        m, c = fresh(M, td)
        m.put("k", "old", provenance=P, timestamp=400.0)
        m.put("k", "new", provenance=P)  # second current value at t=1000: a contradiction
        before = m.recall("k", threshold=0.0)
        c.t = 500.0
        after = m.recall("k", threshold=0.0)
    hidden = before["status"] == "UNKNOWN" and after["status"] == "KNOWN"
    record("A8", "defect_contradiction_hidden" if hidden else "clean",
           before=before["status"] + ":" + before.get("reason", ""),
           after=after["status"] + ":" + str(after.get("value", after.get("reason"))))


# ---------------------------------------------------------------- A9-A11, A13-A15

def a9(M):
    bad = ["\ud800", "a\udfffb", "x\x00y", "‮evil", " ", "\t\n"]
    out = {}
    with tempfile.TemporaryDirectory() as td:
        m, c = fresh(M, td)
        i = m.put("k", "v", provenance=P)
        for s in bad:
            for field in ("key", "value", "text", "source", "reason"):
                before = m.path.read_bytes()
                try:
                    if field == "key":
                        m.put(s, "v", provenance=P)
                    elif field == "value":
                        m.put("k2", s, provenance=P)
                    elif field == "text":
                        m.put("k3", "v", provenance=P, text=s)
                    elif field == "source":
                        m.put("k4", "v", provenance={**P, "source": s})
                    else:
                        m.revoke(i, reason=s, provenance=P)
                    res = "accepted"
                except ValueError:
                    res = "ValueError"
                except Exception as e:  # noqa: BLE001
                    res = f"other:{type(e).__name__}"
                changed = m.path.read_bytes() != before
                out[f"{field}:{s!r}"] = res + (":changed" if changed else "")
                if res == "accepted" and field == "reason":  # undo for next case
                    break
            try:
                M.MemoryStore(m.path.parent).snapshot()
            except Exception as e:  # noqa: BLE001
                out["REOPEN_AFTER_" + repr(s)] = f"FAILED:{type(e).__name__}"
    others = {k: v for k, v in out.items() if v.startswith("other") or v.startswith("FAILED")}
    accepted = {k: v for k, v in out.items() if v.startswith("accepted")}
    record("A9", "clean" if not others else "defect", other_exceptions=others, accepted=accepted)


def a10(M):
    out = {}
    with tempfile.TemporaryDirectory() as td:
        m = build_valid(M, td)
        d = m.path.parent
        good = m.path.read_bytes()
        (d / "memory.lock").unlink()
        (d / "memory.lock").mkdir()
        out["lock_is_directory"] = classify_load(M, d)[0]
        (d / "memory.lock").rmdir()
        m.path.unlink()
        out["data_missing"] = classify_load(M, d)[0]
        m.path.mkdir()
        out["data_is_directory"] = classify_load(M, d)[0]
        m.path.rmdir()
        m.path.write_bytes(good)
        out["restored"] = classify_load(M, d)[0]
    record("A10", "clean" if all(v == "integrity" for k, v in out.items() if k != "restored") else "defect", **out)


def a11(M):
    out = {}
    with tempfile.TemporaryDirectory() as td:
        m, c = fresh(M, td, max_records=5)
        for i in range(5):
            m.put(f"k{i}", "v", provenance=P, protected=True)
        before = m.path.read_bytes()
        for name, fn in [("put", lambda: m.put("x", "v", provenance=P)),
                         ("correct", lambda: m.correct(1, "v2", provenance=P)),
                         ("compact", lambda: m.compact(2))]:
            try:
                fn()
                out[name] = "allowed"
            except (M.CapacityError, ValueError) as e:
                out[name] = type(e).__name__
            except Exception as e:  # noqa: BLE001
                out[name] = f"other:{type(e).__name__}"
        out["unchanged"] = m.path.read_bytes() == before
        try:
            m.revoke(1, reason="r", provenance=P)
            out["revoke_at_record_cap"] = "allowed (no new record needed)"
        except Exception as e:  # noqa: BLE001
            out["revoke_at_record_cap"] = type(e).__name__
    with tempfile.TemporaryDirectory() as td:
        m, c = fresh(M, td, max_bytes=4096)
        n = 0
        try:
            while True:
                m.put(f"k{n}", "v" * 200, provenance=P, protected=True)
                n += 1
        except M.CapacityError:
            out["byte_cap_records"] = n
        except Exception as e:  # noqa: BLE001
            out["byte_cap_records"] = f"other:{type(e).__name__}"
        out["byte_cap_file_le_limit"] = m.path.stat().st_size <= 4096
        before = m.path.read_bytes()
        try:
            m.revoke(1, reason="r" * 50, provenance=P)
            out["revoke_at_byte_cap"] = "allowed"
        except Exception as e:  # noqa: BLE001
            out["revoke_at_byte_cap"] = type(e).__name__
        out["revoke_at_byte_cap_unchanged_if_refused"] = (m.path.read_bytes() == before) or out["revoke_at_byte_cap"] == "allowed"
    bad = [k for k, v in out.items() if str(v).startswith("other") or v is False or v == "allowed"]
    record("A11", "clean" if not bad else "defect", **out)


def a13(M):
    vecs = {"all_1e-200": [1e-200] * 384, "all_1e-160": [1e-160] * 384,
            "mixed_1e100_1e-100": [1e100 if i % 2 else 1e-100 for i in range(384)],
            "signed_zeros_plus_one": [-0.0] * 383 + [1.0], "single_tiny": [0.0] * 383 + [1e-300]}
    out = {}
    with tempfile.TemporaryDirectory() as td:
        m, c = fresh(M, td)
        for name, v in vecs.items():
            try:
                m.put("k", name, provenance=P, embedding=v)
                out[name] = "stored"
            except ValueError:
                out[name] = "ValueError"
            except Exception as e:  # noqa: BLE001
                out[name] = f"other:{type(e).__name__}"
        out["reopen"] = classify_load(M, m.path.parent)[0]
    record("A13", "clean" if out["reopen"] == "ok" and not any(str(v).startswith("other") for v in out.values())
           else "defect", **out)


def a14(M):
    with tempfile.TemporaryDirectory() as td:
        m, c = fresh(M, td)
        m.put("k", "v1", provenance=P)
        old = m.path.read_bytes()
        c.t += 1
        m.correct(1, "v2", provenance=P)
        m.revoke(2, reason="withdrawn", provenance=P)
        m.path.write_bytes(old)
        cls, snap = classify_load(M, m.path.parent)
        rolled_back = cls == "ok" and snap["generation"] == 1
    record("A14", "rollback_accepted" if rolled_back else f"rollback_{cls}")


def a15(M, policies):
    with tempfile.TemporaryDirectory() as td:
        m, c = fresh(M, td)
        r = policies.admit(m, "protected", "k", "v", provenance=P, force_scar=True, thermal_state="SCAR_LOCK")
    record("A15", "observed", force_scar_under_scar_lock=r)


# ---------------------------------------------------------------- A12: model-based sequences

def model_compact(model, target):
    roots, groups = {}, {}
    for r in sorted(model, key=lambda x: x["id"]):
        root = roots[r["supersedes"]] if r["supersedes"] is not None else r["id"]
        roots[r["id"]] = root
        groups.setdefault(root, []).append(r)
    removable = sorted((g for g in groups.values() if not any(x["protected"] for x in g)),
                       key=lambda g: (max(x["weight"] for x in g), g[0]["id"]))
    count, removed = len(model), set()
    for g in removable:
        if count <= target:
            break
        removed |= {x["id"] for x in g}
        count -= len(g)
    if count > target:
        return None
    return [r for r in model if r["id"] not in removed]


def a12(M, sequences=300, length=40, seed=99):
    rng = random.Random(seed)
    mismatches = []
    ops_run = 0
    for sq in range(sequences):
        with tempfile.TemporaryDirectory() as td:
            m, c = fresh(M, td, max_records=12)
            model, next_id = [], 1
            for step in range(length):
                c.t += 1
                op = rng.choice(["put", "put", "correct", "revoke", "compact", "recall", "recall"])
                key = rng.choice(["alpha", "beta", "gamma"])
                before = m.path.read_bytes()
                ops_run += 1
                try:
                    if op == "put":
                        prot = rng.random() < .3
                        w = rng.choice([.1, .5, .9])
                        expect_ok = len(model) < 12
                        try:
                            i = m.put(key, rng.choice(["x", "y"]), provenance=P, protected=prot, weight=w)
                            got_ok = True
                        except M.CapacityError:
                            got_ok = False
                        if got_ok != expect_ok:
                            raise AssertionError(f"put ok={got_ok} expected {expect_ok}")
                        if got_ok:
                            if i != next_id:
                                raise AssertionError(f"id {i} expected {next_id}")
                            rec = m.snapshot()["records"][-1]
                            model.append({"id": i, "key": key, "value": rec["value"], "status": "current",
                                          "protected": prot, "weight": w, "supersedes": None})
                            next_id += 1
                    elif op == "correct":
                        tid = rng.randrange(0, next_id + 2)
                        t = next((r for r in model if r["id"] == tid), None)
                        expect_ok = t is not None and t["status"] == "current" and len(model) < 12 and tid >= 1
                        try:
                            i = m.correct(tid, "z", provenance=P)
                            got_ok = True
                        except (ValueError, M.CapacityError):
                            got_ok = False
                        if got_ok != expect_ok:
                            raise AssertionError(f"correct({tid}) ok={got_ok} expected {expect_ok}")
                        if got_ok:
                            t["status"] = "superseded"
                            model.append({"id": i, "key": t["key"], "value": "z", "status": "current",
                                          "protected": False, "weight": 1.0, "supersedes": tid})
                            next_id += 1
                    elif op == "revoke":
                        tid = rng.randrange(0, next_id + 2)
                        t = next((r for r in model if r["id"] == tid), None)
                        expect_ok = t is not None and t["status"] == "current"
                        try:
                            m.revoke(tid, reason="r", provenance=P)
                            got_ok = True
                        except (ValueError, M.CapacityError):
                            got_ok = False
                        if got_ok != expect_ok:
                            raise AssertionError(f"revoke({tid}) ok={got_ok} expected {expect_ok}")
                        if got_ok:
                            t["status"] = "revoked"
                    elif op == "compact":
                        target = rng.randrange(0, 13)
                        expected = model_compact(model, target)
                        try:
                            m.compact(target)
                            got_ok = True
                        except M.CapacityError:
                            got_ok = False
                        if got_ok != (expected is not None):
                            raise AssertionError(f"compact({target}) ok={got_ok}")
                        if got_ok:
                            model = expected
                    else:
                        cur = [r for r in model if r["key"] == key and r["status"] == "current"]
                        vals = {r["value"] for r in cur}
                        got = m.recall(key, threshold=0.0)
                        exp = "KNOWN" if len(vals) == 1 else "UNKNOWN"
                        if got["status"] != exp or (exp == "KNOWN" and got["value"] not in vals):
                            raise AssertionError(f"recall({key}) got {got['status']}:{got.get('value')} "
                                                 f"expected {exp}:{vals}")
                    if op in ("put", "correct", "revoke", "compact"):
                        snap = m.snapshot()["records"]
                        got_state = [(r["id"], r["key"], r["status"]) for r in snap]
                        exp_state = [(r["id"], r["key"], r["status"]) for r in model]
                        if got_state != exp_state:
                            raise AssertionError(f"state mismatch after {op}")
                except AssertionError as e:
                    mismatches.append({"seq": sq, "step": step, "op": op, "err": str(e)[:160]})
                    break
                except Exception as e:  # noqa: BLE001
                    mismatches.append({"seq": sq, "step": step, "op": op, "err": f"{type(e).__name__}: {e}"[:160],
                                       "unchanged": m.path.read_bytes() == before})
                    break
    record("A12", "clean" if not mismatches else "defect", sequences=sequences, ops=ops_run,
           mismatches=len(mismatches), first=mismatches[:3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--json")
    a = ap.parse_args()
    target = Path(a.target).resolve()
    M, policies = load_target(target)
    only = set(filter(None, a.only.split(",")))
    plan = [("A1", lambda: a1(M)), ("A2", lambda: a2(M)), ("A3", lambda: a3(M)), ("A4", lambda: a4(M)),
            ("A5", lambda: a5(M, target)), ("A6", lambda: a6(M, target)), ("A7", lambda: a7(M)),
            ("A8", lambda: a8(M)), ("A9", lambda: a9(M)), ("A10", lambda: a10(M)), ("A11", lambda: a11(M)),
            ("A12", lambda: a12(M)), ("A13", lambda: a13(M)), ("A14", lambda: a14(M)),
            ("A15", lambda: a15(M, policies))]
    print(f"target {target} | memory.py sha256 {hashlib.sha256((target / 'sml' / 'memory.py').read_bytes()).hexdigest()}"
          f" | python {sys.version.split()[0]}", flush=True)
    for aid, fn in plan:
        if not only or aid in only:
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                record(aid, f"HARNESS_ERROR:{type(e).__name__}", detail=str(e)[:300])
    if a.json:
        Path(a.json).write_text(json.dumps(RESULTS, indent=1, default=str))


if __name__ == "__main__":
    main()
