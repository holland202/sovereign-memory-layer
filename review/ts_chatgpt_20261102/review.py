#!/usr/bin/env python3
"""Independent, bounded, source-informed review registered in PREREG.md.

Run from repository root. Exit 1: differences/contract failures; 2: runner failure.
--case selects one reproducible case. --mutant changes a successful put response,
without changing ts/src or its writes; the control comparison must catch it.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from sml import memory as M  # noqa: E402

E = [1.0] + [0.0] * 383
PROV = {"source": "synthetic-review", "locator": "ts-review-20261102", "sha256": hashlib.sha256(b"synthetic").hexdigest()}
CREATE = {"op": "create", "clock": 1000, "max_records": 12, "max_bytes": 2000000}
PUT = {"op": "put", "clock": 1000, "key": "alpha", "value": "one", "provenance": PROV, "embedding": E}
ABSENT = object()


@dataclass
class Raw:
    text: str


def encode(value):
    if isinstance(value, Raw):
        return value.text
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + ":" + encode(v) for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(map(encode, value)) + "]"
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


@dataclass
class Case:
    name: str
    ops: list = field(default_factory=list)
    fixture: bytes | None = None
    expected: dict = field(default_factory=dict)
    declared: str | None = None
    path_setup: str | None = None


class Side:
    def __init__(self, label, command, out):
        self.label = label
        self.requests = (out / (label + ".requests.jsonl")).open("wb")
        self.responses = (out / (label + ".responses.jsonl")).open("wb")
        self.stderr = (out / (label + ".stderr")).open("wb")
        self.command = command
        self.p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, bufsize=0)
        self.buffer = b""

    def ask(self, line):
        data = line.encode("utf-8") + b"\n"
        self.requests.write(data)
        self.requests.flush()
        self.p.stdin.write(data)
        deadline = time.monotonic() + 15
        while b"\n" not in self.buffer:
            if time.monotonic() >= deadline:
                raise TimeoutError(self.label + " response timed out")
            ready, _, _ = select.select([self.p.stdout], [], [], min(1, deadline - time.monotonic()))
            if ready:
                chunk = os.read(self.p.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError(self.label + " died, code=" + str(self.p.poll()))
                self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        self.responses.write(line + b"\n")
        self.responses.flush()
        return line.decode("utf-8")

    def close(self):
        self.p.stdin.close()
        try:
            code = self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()
            code = self.p.wait()
        for f in (self.requests, self.responses, self.stderr):
            f.close()
        return {"command": self.command, "exit_code": code}


def env_bytes(payload):
    return M.canonical({"payload": payload, "sha256": M.digest(payload)}) + b"\n"


def record(i, key="alpha", value="one", **changes):
    r = {"id": i, "key": key, "value": value, "text": key + " " + value, "provenance": copy.deepcopy(PROV),
         "timestamp": 1000.0, "recorded_at": 1000.0, "weight": 1.0, "protected": False,
         "status": "current", "supersedes": None, "revocation": None, "embedding": E.copy()}
    return {**r, **changes}


def snapshot(records=(), **changes):
    state = {"schema": 1, "generation": len(records), "next_id": max([r["id"] for r in records] + [0]) + 1,
             "max_records": 12, "max_bytes": 2000000, "records": list(records)}
    return env_bytes({**state, **changes})


def stored_case(name, op, **kwargs):
    return Case(name, [CREATE.copy(), op], **kwargs)


def cases():
    out = [Case("C0_control", [CREATE.copy(), {**PUT, "protected": True},
        {"op": "retrieve", "query": "alpha", "qembedding": E, "threshold": 0},
        {"op": "recall", "key": "alpha", "qembedding": E, "threshold": 0},
        {**PUT, "op": "correct", "id": 1, "value": "two"},
        {"op": "recall", "key": "alpha", "qembedding": E, "threshold": 0},
        {"op": "compact", "target": 0},
        {"op": "revoke", "id": 2, "reason": "withdraw", "provenance": PROV},
        {"op": "recall", "key": "alpha", "qembedding": E, "threshold": 0},
        {"op": "status"}], expected={0: {"ok": True, "result": None}, 1: {"ok": True, "result": 1},
        2: {"ok": True, "result": [[1, "1.0"]]},
        3: {"ok": True, "result": {"status": "KNOWN", "value": "one", "evidence_ids": [1], "hits": [[1, "1.0"]]}},
        4: {"ok": True, "result": 2},
        5: {"ok": True, "result": {"status": "KNOWN", "value": "two", "evidence_ids": [2], "hits": [[2, "1.0"]]}},
        6: {"ok": False, "error": "CapacityError"}, 7: {"ok": True, "result": None},
        8: {"ok": True, "result": {"status": "UNKNOWN", "reason": "insufficient_evidence", "evidence_ids": []}}})]
    strings = ["🙂key", "𐀀", "\uffff", "𐐀𐐨", "café", "cafe\u0301", "a🙂𐐀\ue000z", "quote\"\\", "k\u2028x"]
    for i, text in enumerate(strings):
        op = {**PUT, "key": text, "value": "value " + text, "text": "text " + text,
              "provenance": {**PROV, "source": "source" + text, "locator": "locator" + text}}
        out.append(Case(f"A1_astral_{i:02}", [CREATE.copy(), op,
            {"op": "recall", "key": unicodedata.normalize("NFD", text), "query": "text " + text, "qembedding": E, "threshold": 0},
            {**op, "op": "correct", "id": 1, "value": "corrected🙂"}, {"op": "status"}]))
    for i, text in enumerate(["\x00", "\u200b", "\u202e", "\ud800", "\udfff"]):
        for fieldname in ("key", "value", "text"):
            out.append(stored_case(f"A1_invalid_{i}_{fieldname}", {**PUT, fieldname: "a" + text + "b"}))
    tokens = ["-0", "-0.0", "0", "1", "1.0", "1E5", "1e-4000", "-1e-4000", "1e400", "-1e400",
              "9007199254740991", "9007199254740992", "9007199254740993", "9007199254740994",
              "-9223372036854775808", "9223372036854775806", "9223372036854775807",
              "9223372036854775808", "-9223372036854775809", "9" * 500, "9" * 4301,
              "0.99999999999999999", "5e-324", "2.2250738585072014e-308"]
    for i, token in enumerate(tokens):
        declared = "outside signed i64" if i in (17, 18, 19, 20) else None
        for f in ("clock", "weight", "timestamp"):
            out.append(stored_case(f"A3_number_{i:02}_{f}", {**PUT, f: Raw(token)}, declared=declared))
        out.append(Case(f"A3_number_{i:02}_id", [CREATE.copy(), PUT.copy(),
            {"op": "correct", "id": Raw(token), "value": "two", "embedding": E, "provenance": PROV}], declared=declared))
        out.append(stored_case(f"A3_number_{i:02}_unused", {"op": "status", "unused": Raw(token)}, declared=declared))
        out.append(stored_case(f"A3_number_{i:02}_embedding", {**PUT, "embedding": [Raw(token)] + [1.0] * 383}, declared=declared))
    for value in (True, False, 1.0, None, "1"):
        suffix = encode(value).replace('"', "")
        for f in ("max_records", "max_bytes"):
            out.append(Case(f"A4_{f}_{suffix}", [{**CREATE, f: value}]))
        for opname, f, other in [("compact", "target", {}), ("retrieve", "top_k", {"query": "alpha"}),
                                ("correct", "id", {"value": "two", "provenance": PROV}),
                                ("revoke", "id", {"reason": "withdraw", "provenance": PROV})]:
            out.append(Case(f"A4_{opname}_{suffix}", [CREATE.copy(), PUT.copy(), {"op": opname, f: value, **other}]))
        for f in ("weight", "clock", "timestamp"):
            out.append(stored_case(f"A4_put_{f}_{suffix}", {**PUT, f: value}))
        out.append(stored_case(f"A4_embedding_{suffix}", {**PUT, "embedding": [value] + [1.0] * 383}))
    texts = ["ΟΣ", "ΟΣ Α", "AΣ", "AΣ\u0301", "AΣ'A", "AΣ🙂", "Σ", "ΣΑΣ ΟΔΟΣ", "İ i ı I",
             "ẞ ß", "𐐀 𐐧 𐐨", "a\x1cb\x85c\u00a0d\u3000e", "Cafe\u0301 CAFÉ", "a\u0345Σ"]
    for i, t in enumerate(texts):
        op = {**PUT, "text": t}
        del op["embedding"]
        out.append(Case(f"A5_casing_{i:02}", [CREATE.copy(), op, {"op": "retrieve", "query": t, "threshold": 0}]))
    for i, val in enumerate([ABSENT, None, False, 0, [], {}, "", "alpha", 1, True]):
        op = {"op": "recall", "key": "alpha", "threshold": 0}
        if val is not ABSENT:
            op["query"] = val
        out.append(Case(f"A6_recall_query_{i:02}", [CREATE.copy(), PUT.copy(), op]))
    for f in ("top_k", "threshold", "half_life", "method", "rkey", "qembedding"):
        for val in (None, False, 0, [], {}, ""):
            out.append(Case(f"A6_recall_{f}_{encode(val)}", [CREATE.copy(), PUT.copy(),
                {"op": "recall", "key": "alpha", f: val}]))
    for f in ("max_records", "max_bytes"):
        op = CREATE.copy()
        del op[f]
        out.append(Case(f"A6_create_missing_{f}", [op]))
    for f in ("weight", "timestamp", "text", "embedding", "thermal_state", "supersedes", "provenance", "protected"):
        out.append(stored_case(f"A6_put_null_{f}", {**PUT, f: None}))
    for val in (None, False, 0, [], {}):
        out.append(Case(f"A7_repr_dir_{encode(val)}", [{"op": "repr", "dir": val, "bits": ["3ff0000000000000"]}]))
        out.append(Case(f"A7_bad_create_dir_{encode(val)}", [{**CREATE, "dir": val, "max_records": False}]))
    for op in ({**PUT, "key": "", "weight": False}, {"op": "correct", "id": False},
               {"op": "retrieve", "query": None, "method": "bogus"}):
        out.append(Case(f"A7_absent_{len(out)}", [op]))
        out.append(Case(f"A7_corrupt_{len(out)}", [op], fixture=b'{"broken":true}\n'))
    out += [Case("A7_full_bad_target", [{**CREATE, "max_records": 1}, PUT.copy(), {**PUT, "supersedes": 999}]),
            Case("A7_full_resource", [{**CREATE, "max_records": 1}, PUT.copy(), {**PUT, "key": "", "thermal_state": "SCAR_LOCK"}]),
            Case("A7_lock_directory", [{"op": "status"}], fixture=snapshot(), path_setup="lock_dir"),
            Case("A7_pending_directory", [{"op": "cleanup"}], fixture=snapshot(), path_setup="pending_dir")]
    for base in (2**53, 2**63 - 4):
        for different in (False, True):
            rs = [record(base), record(base + 1, key="beta" if different else "alpha", value="two")]
            for opname in ("correct", "put"):
                op = {**PUT, "op": opname, "value": "three", "id": base + 1, "supersedes": base + 1,
                      "key": "beta" if different else "alpha"}
                out.append(Case(f"A8_highid_{base}_{different}_{opname}", [{"op": "status"}, op, {"op": "status"}], fixture=snapshot(rs)))
    for fieldname in ("generation", "next_id"):
        for n in (2**63 - 2, 2**63 - 1):
            out.append(Case(f"A8_counter_{fieldname}_{n}", [{"op": "status"}, PUT.copy(), {"op": "status"}],
                            fixture=snapshot(**{fieldname: n})))
    for weights in ((1, 0), (1.0, 0), (1, 0.0), (1.0, 0.0)):
        rs = [record(1, weight=weights[0]), record(2, key="beta", weight=weights[1])]
        out.append(Case("A8_weight_types_" + "_".join(type(x).__name__ for x in weights),
                        [{"op": "status"}, {"op": "compact", "target": 1}, {"op": "status"}], fixture=snapshot(rs)))
    for t in (1000, 1000.0, Raw("-0")):
        timestamp = 0 if isinstance(t, Raw) else t
        rs = [record(1, timestamp=timestamp, recorded_at=1000.0)]
        out.append(Case(f"A8_revoke_timestamp_{type(t).__name__}", [{"op": "status"},
            {"op": "revoke", "clock": 900, "id": 1, "reason": "withdraw", "provenance": PROV}, {"op": "status"}], fixture=snapshot(rs)))
    rs = [record(1, embedding=[1] + [0] * 383, weight=1, timestamp=1000, recorded_at=1000)]
    out.append(Case("A8_integer_stored_numbers", [{"op": "status"}, {"op": "retrieve", "query": "alpha", "qembedding": E}], fixture=snapshot(rs)))
    for name, data in [("invalid_utf8", b"\xff"), ("bad_checksum", snapshot().replace(b'"sha256":"', b'"sha256":"0', 1)),
                       ("bool_schema", snapshot(schema=True)), ("float_counter", snapshot(generation=0.0)),
                       ("negative_counter", snapshot(generation=-1)), ("utf8_bom", b"\xef\xbb\xbf" + snapshot()),
                       ("utf16", snapshot().decode().encode("utf-16")), ("utf32", snapshot().decode().encode("utf-32"))]:
        out.append(Case("A8_file_" + name, [{"op": "status"}], fixture=data,
                        declared="UTF-16/32" if name in ("utf16", "utf32") else None))
    return out


def blob(directory):
    p = directory / "memory.json"
    return p.read_bytes() if p.is_file() else None


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def helpers(adapter, out, event):
    problems = []
    examples = [{"𐀀": 1, "\ue000": 2, "\uffff": 3, "a": 4, "🙂": 5},
                {"z": {"𐐀": 1, "\ue001": 2}, "a": ["🙂", "\x00\n\t", -0.0, 1e5]},
                {"𐀀a": 1, "𐀀": 2, "a𐀀": 3, "a\ue000": 4}]
    for i, value in enumerate(examples):
        req = {"action": "canonical", "value": value}
        expected = {"ok": True, "result": M.canonical(value).hex()}
        actual = json.loads(adapter.ask(encode(req)))
        ev = {"case": f"A2_sort_{i}", "input": req, "expected": expected, "actual": actual}
        event(ev)
        if expected != actual:
            problems.append(ev)
    for i, text in enumerate(["ΟΣ", "AΣ\u0301", "İ i ı I", "𐐀 𐐧", "a\x1cb\x85c\u3000d"]):
        req = {"action": "hash", "value": text}
        expected = {"ok": True, "result": M.canonical(M.hash_embedding(text)).hex()}
        actual = json.loads(adapter.ask(encode(req)))
        ev = {"case": f"A5_hash_{i}", "input": req, "expected": expected, "actual": actual}
        event(ev)
        if expected != actual:
            problems.append(ev)
    boundary = [0.0, -0.0, 5e-324, -5e-324, -math.log(2), -1e-9, -512.0, -700.0, -744.0, -745.0, -746.0,
                709.0, math.nextafter(709.0, math.inf)]
    for i, value in enumerate(boundary):
        hx = lambda x: struct.pack(">d", x).hex()
        req = {"action": "exp", "value": hx(value)}
        expected = {"ok": True, "result": hx(math.exp(value))}
        actual = json.loads(adapter.ask(encode(req)))
        ev = {"case": f"B2_boundary_{i}", "input": req, "expected": expected, "actual": actual}
        event(ev)
        if expected != actual:
            problems.append(ev)
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(HERE / "raw" / "attacks"))
    parser.add_argument("--case", default="")
    parser.add_argument("--mutant", action="store_true")
    parser.add_argument("--rust-bin")
    a = parser.parse_args()
    out = Path(a.out).resolve()
    if out.exists():
        raise FileExistsError("refuse to overwrite an evidence directory: " + str(out))
    out.mkdir(parents=True)
    evidence = (out / "events.jsonl").open("w")
    event = lambda x: (evidence.write(json.dumps(x, ensure_ascii=True) + "\n"), evidence.flush())
    summary = {"target": "e1ad1ae03aab8feb924b53365b4e943750026487", "command": sys.argv,
               "python": sys.version, "node": subprocess.check_output(["node", "--version"], text=True).strip(),
               "libc": platform.libc_ver(), "machine": platform.machine(), "unicode_python": unicodedata.unidata_version,
               "mutant": a.mutant, "cases": 0, "steps": 0, "failed_cases": [], "declared_differences": [],
               "helper_failures": [], "cross_open_failures": [], "processes": {}}
    ts_command = [sys.executable, str(HERE / "mutant.py")] if a.mutant else ["node", str(ROOT / "ts/src/cli.ts")]
    sides = {"py": Side("py", [sys.executable, str(ROOT / "tools/py_cli.py"), str(ROOT)], out),
             "ts": Side("ts", ts_command, out)}
    if a.rust_bin:
        sides["rust"] = Side("rust", [str(Path(a.rust_bin).resolve())], out)
    adapter = Side("adapter", ["node", str(HERE / "adapter.ts")], out)
    temp = tempfile.TemporaryDirectory(prefix="sml-ts-review-")
    root = Path(temp.name)
    try:
        selected = [c for c in cases() if not a.case or c.name == a.case]
        if not selected:
            raise ValueError("unknown case " + a.case)
        for ci, case in enumerate(selected):
            summary["cases"] += 1
            dirs = {label: root / f"case{ci}" / label for label in sides}
            for d in dirs.values():
                d.parent.mkdir(parents=True, exist_ok=True)
                if case.fixture is not None:
                    d.mkdir()
                    (d / "memory.json").write_bytes(case.fixture)
                if case.path_setup:
                    (d / ("memory.lock" if case.path_setup == "lock_dir" else "memory.pending")).mkdir()
            if case.fixture is not None:
                fixtures = out / "fixtures"
                fixtures.mkdir(exist_ok=True)
                (fixtures / (case.name + ".bin")).write_bytes(case.fixture)
                event({"case": case.name, "fixture_sha256": digest(case.fixture), "declared": case.declared})
            differences = []
            for oi, op in enumerate(case.ops):
                summary["steps"] += 1
                responses, snapshots, before, hashes = {}, {}, {}, {}
                for label, side in sides.items():
                    before[label] = blob(dirs[label])
                    request = {"clock": 1000, "dir": str(dirs[label]), **op}
                    line = side.ask(encode(request))
                    responses[label] = line
                    snapshots[label] = blob(dirs[label])
                    hashes[label] = digest(snapshots[label])
                ev = {"case": case.name, "step": oi, "input": encode(op), "raw_responses": responses,
                      "snapshot_sha256": hashes, "snapshot_before_sha256": {k: digest(v) for k, v in before.items()},
                      "declared": case.declared, "mismatches": []}
                if len(set(responses.values())) != 1:
                    ev["mismatches"].append("protocol response")
                if len(set(hashes.values())) != 1:
                    ev["mismatches"].append("snapshot bytes")
                for label, response in responses.items():
                    parsed = json.loads(response)
                    if oi in case.expected and parsed != case.expected[oi]:
                        ev["mismatches"].append(label + " independent control expectation")
                    if not parsed.get("ok") and parsed.get("error") != "CommitUncertain" and snapshots[label] != before[label]:
                        ev["mismatches"].append(label + " refused operation changed snapshot")
                if ev["mismatches"]:
                    differences.append(oi)
                    bad = out / "snapshots" / case.name
                    bad.mkdir(parents=True, exist_ok=True)
                    for label, data in snapshots.items():
                        if data is not None:
                            (bad / f"{oi}_{label}.json").write_bytes(data)
                event(ev)
            if differences:
                (summary["declared_differences"] if case.declared else summary["failed_cases"]).append(
                    {"case": case.name, "steps": differences, "declared": case.declared})
            # Actual cross-opening, sequentially, after every case with agreeing files.
            images = {k: blob(d) for k, d in dirs.items()}
            if all(x is not None for x in images.values()) and len({digest(x) for x in images.values()}) == 1:
                for label, side in sides.items():
                    other = "ts" if label == "py" else "py"
                    before_cross = blob(dirs[other])
                    response = side.ask(encode({"op": "status", "dir": str(dirs[other]), "clock": 1000}))
                    own = side.ask(encode({"op": "status", "dir": str(dirs[label]), "clock": 1000}))
                    mismatch = response != own or blob(dirs[other]) != before_cross
                    event({"case": case.name, "cross_open": label + " on " + other, "response": response,
                           "own_response": own, "mismatch": mismatch})
                    if mismatch:
                        summary["cross_open_failures"].append(case.name + ":" + label)
        if not a.case:
            summary["helper_failures"] = helpers(adapter, out, event)
        if a.mutant:
            summary["sabotage_caught"] = bool(summary["failed_cases"])
    except Exception as exc:
        summary["runner_error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        for label, side in [*sides.items(), ("adapter", adapter)]:
            summary["processes"][label] = side.close()
        evidence.close()
        temp.cleanup()
        (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("processes", "helper_failures")}, indent=2))
    defects = bool(summary["failed_cases"] or summary["helper_failures"] or summary["cross_open_failures"])
    if a.mutant:
        print("SABOTAGE CAUGHT" if summary["sabotage_caught"] else "SABOTAGE NOT CAUGHT")
        return 0 if summary["sabotage_caught"] else 1
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
