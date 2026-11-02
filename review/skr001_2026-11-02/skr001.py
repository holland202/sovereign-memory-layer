#!/usr/bin/env python3
"""SKR-001 harness: same-key writers racing, one SIGKILLed at a commit boundary.

Registered in PREREG.md (commit ceb76ff) before this file existed.
Usage: python3 review/skr001_2026-11-02/skr001.py [--sabotage]
Exit 0 only when all six registered predictions hold. Under --sabotage the registered
expectation is a failure of P1, P2 or P4, so exit 1 there is the expected outcome.
"""
import json, os, random, signal, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
K, M, TRIALS_PER_STAGE = 4, 25, 8
STAGES = ["partial_write", "after_file_fsync", "after_replace"]
KEY = "race.k"
PROV = {"source": "skr001-synthetic", "locator": "case", "sha256": "a" * 64}

WRITER = r'''
import contextlib, json, os, signal, sys, time
sys.path.insert(0, sys.argv[1])
from sml.memory import MemoryStore
store_dir, wid, victim, kill_at, stage, sabotage, go_file = sys.argv[2:9]
wid, kill_at = int(wid), int(kill_at)
victim, sabotage = victim == "1", sabotage == "1"
waits = []
orig_lock = MemoryStore._lock
@contextlib.contextmanager
def timed_lock(self):
    t0 = time.monotonic()
    with orig_lock(self):
        waits.append(time.monotonic() - t0)
        yield
@contextlib.contextmanager
def no_lock(self):
    yield
MemoryStore._lock = no_lock if sabotage else timed_lock
commits = {"n": 0}
def fault(at):
    if at == "partial_write":
        commits["n"] += 1
    if victim and at == stage and commits["n"] == kill_at:
        sys.stdout.flush()
        os.kill(os.getpid(), signal.SIGKILL)
        time.sleep(10)
m = MemoryStore(store_dir, fault=fault)
while not os.path.exists(go_file):
    time.sleep(0.001)
for n in range(int(sys.argv[9])):
    v = f"w{wid}.{n}"
    try:
        i = m.put("race.k", v, provenance=%r)
    except Exception as e:
        print(json.dumps({"error": type(e).__name__, "value": v}), flush=True)
        break
    print(json.dumps({"ack": i, "value": v}), flush=True)
print(json.dumps({"waits_over_1ms": sum(w > 0.001 for w in waits)}), flush=True)
''' % (PROV,)


def trial(seed, stage, sabotage, td):
    rng = random.Random(seed)
    victim, kill_at = rng.randrange(K), rng.randint(1, M)
    d = Path(td) / f"s{seed}"
    sys.path.insert(0, str(ROOT))
    from sml.memory import MemoryStore
    MemoryStore(d, create=True, max_records=200)
    go = Path(td) / f"go{seed}"
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, str(ROOT), str(d), str(w),
                               "1" if w == victim else "0", str(kill_at), stage,
                               "1" if sabotage else "0", str(go), str(M)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for w in range(K)]
    time.sleep(0.3)
    go.touch()
    acks, overlap, killed, errors = {}, 0, 0, []
    for p in procs:
        out, _ = p.communicate(timeout=120)
        if p.returncode == -signal.SIGKILL:
            killed += 1
        for line in out.splitlines():
            r = json.loads(line)
            if "ack" in r:
                acks[r["ack"]] = r["value"]
            elif "waits_over_1ms" in r:
                overlap += r["waits_over_1ms"]
            elif "error" in r:
                errors.append(r["error"])
    res = {"seed": seed, "stage": stage, "victim": victim, "kill_at": kill_at,
           "killed": killed, "acks": len(acks), "contended_lock_waits": overlap,
           "writer_errors": errors}
    try:
        snap = MemoryStore(d).snapshot()
        res["P1"] = True
    except Exception as e:  # noqa: BLE001
        res.update(P1=False, P1_error=type(e).__name__)
        for k in ("P2", "P3", "P4", "P5", "P6"):
            res[k] = False
        return res
    recs = {r["id"]: r for r in snap["records"]}
    res["records"] = len(recs)
    res["P2"] = all(i in recs and recs[i]["value"] == v for i, v in acks.items())
    unacked = [i for i in recs if i not in acks]
    res["unacked"] = len(unacked)
    res["P3"] = len(unacked) <= (1 if stage == "after_replace" else 0)
    ids = sorted(recs)
    res["P4"] = ids == list(range(1, len(ids) + 1))
    try:
        nid = MemoryStore(d).put("race.after", "x", provenance=PROV)
        res["P5"] = nid == len(ids) + 1
    except Exception as e:  # noqa: BLE001
        res.update(P5=False, P5_error=type(e).__name__)
    try:
        r = MemoryStore(d).recall(KEY)
        cur = {i for i, x in recs.items() if x["key"] == KEY and x["status"] == "current"}
        res["P6"] = (r["status"] == "UNKNOWN" and r["reason"] == "contradictory_current_evidence"
                     and set(r["evidence_ids"]) == cur)
    except Exception as e:  # noqa: BLE001
        res.update(P6=False, P6_error=type(e).__name__)
    return res


def main():
    sabotage = "--sabotage" in sys.argv
    results = []
    with tempfile.TemporaryDirectory() as td:
        seed = 0
        for stage in STAGES:
            for _ in range(TRIALS_PER_STAGE):
                results.append(trial(seed, stage, sabotage, td))
                seed += 1
    for r in results:
        print(json.dumps(r, sort_keys=True))
    held = {}
    for p in ("P1", "P2", "P3", "P4", "P5", "P6"):
        held[p] = all(r[p] for r in results)
        print(f"{p}: {'HELD' if held[p] else 'REFUTED'}  ({sum(r[p] for r in results)}/{len(results)} trials)")
    print(f"trials with a contended lock wait (>1 ms): {sum(r['contended_lock_waits'] > 0 for r in results)}/{len(results)}")
    print(f"trials where the victim died by SIGKILL: {sum(r['killed'] == 1 for r in results)}/{len(results)}")
    n = sum(held.values())
    print(f"VERDICT {n} of 6 as registered{' (SABOTAGE RUN)' if sabotage else ''}")
    if sabotage:
        caught = not (held["P1"] and held["P2"] and held["P4"])
        print("SABOTAGE CAUGHT" if caught else "SABOTAGE NOT CAUGHT: instrument is vacuous")
    sys.exit(0 if n == 6 else 1)


if __name__ == "__main__":
    main()
