"""Small bounded snapshot store. POSIX local filesystems, cooperative writers only.

Checksums detect accidental corruption, not malicious rewriting or rollback.
Scores are retrieval heuristics, never probabilities that evidence is true.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

METHODS = ("similarity", "recency", "importance", "protected")
DIM = 384
RECORD_FIELDS = {"id", "key", "value", "text", "provenance", "timestamp",
                 "recorded_at", "weight", "protected", "status", "supersedes",
                 "revocation", "embedding"}


class CapacityError(RuntimeError):
    """No mutation committed: protected records are never silently discarded."""


class IntegrityError(RuntimeError):
    """Unreadable or invalid state; no empty-store fallback."""


class CommitUncertain(RuntimeError):
    """Replace occurred but durability confirmation failed; reopen before retry."""


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def number(x, name, low=0, high=float("inf")):
    if type(x) not in (int, float) or not math.isfinite(x) or not low <= x <= high:
        raise ValueError(f"invalid {name}")
    return float(x)


def nonempty(x, name):
    if not isinstance(x, str) or not x.strip():
        raise ValueError(f"empty {name}")
    return x


def identifier(x, name):
    """ATK E1/E2: a key or provenance identifier is NFC-normalized and has no control/format characters."""
    nonempty(x, name)
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs") for ch in x):
        raise ValueError(f"{name} contains control, format or surrogate characters")
    return unicodedata.normalize("NFC", x)


def same_key(a, b):
    return isinstance(a, str) and isinstance(b, str) and \
        unicodedata.normalize("NFC", a) == unicodedata.normalize("NFC", b)


def validate_provenance(p):
    if not isinstance(p, dict) or set(p) != {"source", "locator", "sha256"}:
        raise ValueError("provenance requires source, locator, sha256")
    nonempty(p["source"], "source")
    nonempty(p["locator"], "locator")
    if not isinstance(p["sha256"], str) or len(p["sha256"]) != 64 or any(
            c not in "0123456789abcdef" for c in p["sha256"]):
        raise ValueError("invalid source digest")
    return copy.deepcopy(p)


def vector(xs, dim=DIM):
    if not isinstance(xs, (list, tuple)) or len(xs) != dim:
        raise ValueError("embedding dimension mismatch")
    v = [number(x, "embedding", -1e100, 1e100) for x in xs]
    norm = math.sqrt(sum(x*x for x in v))
    if not norm:
        raise ValueError("zero embedding")
    return [x/norm for x in v]


def hash_embedding(text, dim=DIM):
    """Historical position-weighted lexical hash fallback, NOT neural semantics."""
    nonempty(text, "text")
    out = [0.0] * dim
    for i, word in enumerate(text.lower().split()):
        raw = word.encode("utf-8")
        out[int(hashlib.md5(raw, usedforsecurity=False).hexdigest(), 16) % dim] += 1/(i+1)
        out[int(hashlib.sha256(raw).hexdigest(), 16) % dim] += 0.5/(i+1)
    return vector(out, dim)


def importance(governance=0.5, entropy=1.0, residual=1.0):
    """Recovered core.py formula. Input scaling is absent from the June spec."""
    g = number(governance, "governance", 0, 1)
    h = number(entropy, "entropy")
    r = number(residual, "residual")
    raw = .40*g + .35*min(h/10, 1) + .25*min(r/5, 1)
    return 1/(1+math.exp(-10*(raw-.5)))


class OrthoProjection:
    """Optional fixed BB^T projection, with orthonormal columns represented as rows.

    Basis must come from development data only; this class never fits on queries.
    This is a constrained alternative, not a faithful implementation of random UV^T.
    """
    def __init__(self, basis, dim=DIM):
        if not basis or len(basis) > dim:
            raise ValueError("invalid rank")
        self.basis = [vector(v, dim) for v in basis]
        for i, a in enumerate(self.basis):
            for j, b in enumerate(self.basis):
                if abs(sum(x*y for x, y in zip(a, b)) - (i == j)) > 1e-9:
                    raise ValueError("basis must be orthonormal")
        self.dim = dim
        self.sha256 = digest(self.basis)

    def apply(self, v):
        v = vector(v, self.dim)
        out = [0.0] * self.dim
        for b in self.basis:
            c = sum(x*y for x, y in zip(v, b))
            out = [x + c*y for x, y in zip(out, b)]
        norm = math.sqrt(sum(x*x for x in out))
        return [x/norm for x in out] if norm > 1e-12 else None


class MemoryStore:
    def __init__(self, directory, *, create=False, max_records=128,
                 max_bytes=2_000_000, clock=time.time, fault=None):
        self.directory = Path(directory)
        self.path = self.directory / "memory.json"
        self.pending = self.directory / "memory.pending"
        self.clock = clock
        self.fault = fault or (lambda stage: None)
        self._poisoned = False
        if create:
            if type(max_records) is not int or max_records < 1:
                raise ValueError("invalid max_records")
            if type(max_bytes) is not int or not 1024 <= max_bytes <= 16_000_000:
                raise ValueError("invalid max_bytes")
            # Creation is explicit and refuses any existing directory.
            self.directory.mkdir(mode=0o700)
            with self._lock():
                self._commit({"schema": 1, "generation": 0, "next_id": 1,
                              "max_records": max_records, "max_bytes": max_bytes,
                              "records": []})
        elif not self.directory.is_dir():
            raise IntegrityError("store does not exist; explicit create required")
        with self._lock():
            self._load()

    @contextmanager
    def _lock(self):
        if self._poisoned:
            raise CommitUncertain("reopen store before further use")
        try:
            handle = (self.directory / "memory.lock").open("a+b")
        except OSError as e:  # ATK A10: e.g. the lock path is a directory
            raise IntegrityError(f"cannot open lock file: {e}") from e
        with handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _encode(self, state):
        return canonical({"payload": state, "sha256": digest(state)}) + b"\n"

    def _validate(self, s):
        if not isinstance(s, dict) or set(s) != {"schema", "generation", "next_id",
                "max_records", "max_bytes", "records"} or s["schema"] != 1:
            raise ValueError("invalid snapshot schema")
        for k in ("generation", "next_id", "max_records", "max_bytes"):
            if type(s[k]) is not int or s[k] < (0 if k == "generation" else 1):
                raise ValueError("invalid snapshot counters")
        if not isinstance(s["records"], list) or len(s["records"]) > s["max_records"]:
            raise ValueError("record bound violated")
        ids = set()
        by_id = {}
        for r in s["records"]:
            if not isinstance(r, dict) or set(r) != RECORD_FIELDS:
                raise ValueError("invalid record schema")
            i = r["id"]
            if type(i) is not int or not 0 < i < s["next_id"] or i in ids:
                raise ValueError("invalid or duplicate id")
            ids.add(i)
            by_id[i] = r
            for k in ("key", "value", "text"):
                nonempty(r[k], k)
            validate_provenance(r["provenance"])
            t = number(r["timestamp"], "timestamp")
            number(r["recorded_at"], "recorded_at", t)
            number(r["weight"], "weight", 0, 1)
            if type(r["protected"]) is not bool or r["status"] not in (
                    "current", "superseded", "revoked"):
                raise ValueError("invalid record status")
            vector(r["embedding"])
            if abs(sum(x*x for x in r["embedding"]) - 1) > 1e-8:
                raise ValueError("unnormalized embedding")
            if r["supersedes"] is not None and (type(r["supersedes"]) is not int
                                                or r["supersedes"] >= i):
                raise ValueError("invalid correction link")
            rev = r["revocation"]
            if r["status"] == "revoked":
                if not isinstance(rev, dict) or set(rev) != {"reason", "provenance", "at"}:
                    raise ValueError("invalid revocation")
                nonempty(rev["reason"], "reason")
                validate_provenance(rev["provenance"])
                number(rev["at"], "revocation time", t)
            elif rev is not None:
                raise ValueError("unexpected revocation")
        referenced = set()
        for r in s["records"]:
            target = r["supersedes"]
            if target is not None:
                if target not in by_id or by_id[target]["key"] != r["key"] or target in referenced:
                    raise ValueError("missing, cross-key, or forked correction")
                if by_id[target]["status"] != "superseded" or by_id[target]["timestamp"] > r["timestamp"]:
                    raise ValueError("invalid supersession")
                referenced.add(target)
        if any(r["status"] == "superseded" and r["id"] not in referenced for r in s["records"]):
            raise ValueError("orphan supersession")
        if len(self._encode(s)) > s["max_bytes"]:
            raise ValueError("byte bound violated")

    def _load(self):
        try:
            # Hard defensive input cap; configured envelope bound checked below.
            if self.path.stat().st_size > 16_000_000:
                raise ValueError("snapshot exceeds reader hard limit")
            def pairs(items):
                out = {}
                for k, v in items:
                    if k in out:
                        raise ValueError("duplicate JSON key")
                    out[k] = v
                return out
            env = json.loads(self.path.read_bytes(), object_pairs_hook=pairs)
            if not isinstance(env, dict) or set(env) != {"payload", "sha256"}:
                raise ValueError("invalid envelope")
            s = env["payload"]
            if env["sha256"] != digest(s):  # MUTATION: checksum
                raise ValueError("checksum mismatch")
            self._validate(s)
            return s
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as e:  # ATK A1
            raise IntegrityError(f"{type(e).__name__}: {e}") from e

    def _commit(self, state):
        self._validate(state)
        data = self._encode(state)
        replaced = False
        try:
            with self.pending.open("wb") as handle:
                os.chmod(self.pending, 0o600)
                handle.write(data[:len(data)//2])
                handle.flush()
                self.fault("partial_write")
                handle.write(data[len(data)//2:])
                handle.flush()
                os.fsync(handle.fileno())
            self.fault("after_file_fsync")
            os.replace(self.pending, self.path)
            replaced = True
            self.fault("after_replace")
            fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            self.fault("after_dir_fsync")
        except Exception as e:
            if replaced:
                self._poisoned = True
                raise CommitUncertain("replaced but acknowledgement failed") from e
            raise

    def snapshot(self):
        with self._lock():
            return copy.deepcopy(self._load())

    def storage_status(self):
        with self._lock():
            s = self._load()
            return {"generation": s["generation"], "records": len(s["records"]),
                    "bytes": self.path.stat().st_size,
                    "max_records": s["max_records"], "max_bytes": s["max_bytes"],
                    "incomplete_storage_detected": self.pending.exists()}

    def cleanup_incomplete(self):
        """Explicit removal of an uncommitted temporary file; never promote it."""
        with self._lock():
            self._load()
            self.pending.unlink(missing_ok=True)

    def put(self, key, value, *, provenance, timestamp=None, text=None,
            weight=1.0, protected=False, supersedes=None, embedding=None,
            thermal_state="NOMINAL"):
        if thermal_state not in ("NOMINAL", "THROTTLE", "SCAR_LOCK"):
            raise ValueError("unknown resource state")
        if thermal_state == "SCAR_LOCK":
            raise RuntimeError("resource gate closed, including protected writes")
        key = identifier(key, "key")
        nonempty(value, "value")
        p = validate_provenance(provenance)
        identifier(p["source"], "source")
        identifier(p["locator"], "locator")
        w = number(weight, "weight", 0, 1)
        if type(protected) is not bool:
            raise ValueError("protected must be boolean")
        now = number(self.clock(), "clock")
        ts = now if timestamp is None else number(timestamp, "timestamp", 0, now)
        txt = nonempty(text if text is not None else f"{key} {value}", "text")
        emb = hash_embedding(txt) if embedding is None else vector(embedding)
        with self._lock():
            s = self._load()
            if len(s["records"]) >= s["max_records"]:  # MUTATION: capacity
                raise CapacityError("record capacity exhausted; no write committed")
            if supersedes is not None:
                targets = [r for r in s["records"] if r["id"] == supersedes]
                if not targets or type(supersedes) is not int:
                    raise ValueError("unknown correction target")
                old = targets[0]
                if old["status"] != "current" or not same_key(old["key"], key) or old["timestamp"] > ts:
                    raise ValueError("correction requires current same-key predecessor")
                old["status"] = "superseded"
            i = s["next_id"]
            s["records"].append({"id": i, "key": key, "value": value, "text": txt,
                "provenance": p, "timestamp": ts, "recorded_at": now, "weight": w,
                "protected": protected, "status": "current", "supersedes": supersedes,
                "revocation": None, "embedding": emb})
            s["next_id"] += 1
            s["generation"] += 1
            if len(self._encode(s)) > s["max_bytes"]:
                raise CapacityError("byte capacity exhausted; no write committed")
            self._commit(s)
            return i

    def correct(self, record_id, value, *, provenance, **kwargs):
        if type(record_id) is not int or record_id < 1:
            raise ValueError("positive integer record ID required")
        s = self.snapshot()
        target = next((r for r in s["records"] if r["id"] == record_id), None)
        if target is None:
            raise ValueError("unknown correction target")
        # put revalidates under its lock; protection remains on predecessor.
        return self.put(target["key"], value, provenance=provenance,
                        supersedes=record_id, **kwargs)

    def revoke(self, record_id, *, reason, provenance):
        if type(record_id) is not int or record_id < 1:
            raise ValueError("positive integer record ID required")
        nonempty(reason, "reason")
        p = validate_provenance(provenance)
        with self._lock():
            s = self._load()
            r = next((r for r in s["records"] if r["id"] == record_id), None)
            if r is None or r["status"] != "current":
                raise ValueError("revocation requires a current record")
            r["status"] = "revoked"
            # ATK A7: a clock behind the record's timestamp must not block withdrawal; the
            # revocation time is clamped to the record's timestamp (never earlier).
            r["revocation"] = {"reason": reason, "provenance": p,
                               "at": max(number(self.clock(), "clock"), r["timestamp"])}
            s["generation"] += 1
            if len(self._encode(s)) > s["max_bytes"]:
                raise CapacityError("revocation does not fit; original unchanged")
            self._commit(s)

    def compact(self, target_records):
        """Explicit importance pruning of complete unprotected correction chains.

        No summaries or synthetic facts are created. If protection makes the target
        impossible, fail without committing. No caller receives a false success.
        """
        if type(target_records) is not int or target_records < 0:
            raise ValueError("invalid target_records")
        with self._lock():
            s = self._load()
            groups = {}
            roots = {}
            for r in sorted(s["records"], key=lambda x: x["id"]):
                root = roots[r["supersedes"]] if r["supersedes"] is not None else r["id"]
                roots[r["id"]] = root
                groups.setdefault(root, []).append(r)
            removable = sorted((g for g in groups.values() if not any(r["protected"] for r in g)),
                               key=lambda g: (max(r["weight"] for r in g), g[0]["id"]))
            removed = []
            count = len(s["records"])
            for group in removable:
                if count <= target_records:
                    break
                removed.extend(r["id"] for r in group)
                count -= len(group)
            if count > target_records:
                raise CapacityError("protected chains prevent compaction; unchanged")
            if removed:
                s["records"] = [r for r in s["records"] if r["id"] not in removed]
                s["generation"] += 1
                self._commit(s)
            return removed

    def retrieve(self, query, **kwargs):
        return self._retrieve_from(self.snapshot(), query, **kwargs)

    def _retrieve_from(self, snapshot, query, *, method="similarity", top_k=5, threshold=.15,
                 half_life=30*86400, key=None, embedding=None, projection=None):
        if method not in METHODS:
            raise ValueError("unknown retrieval method")
        if type(top_k) is not int or not 1 <= top_k <= 100:
            raise ValueError("invalid top_k")
        threshold = number(threshold, "threshold", 0, 1)
        half_life = number(half_life, "half_life", 1e-9)
        now = number(self.clock(), "clock")
        q = hash_embedding(query) if embedding is None else vector(embedding)
        if projection:
            q = projection.apply(q)
        if q is None:
            return []
        out = []
        for r in snapshot["records"]:
            if r["status"] != "current":  # MUTATION: supersession
                continue
            if (key is not None and not same_key(r["key"], key)) or r["timestamp"] > now:
                continue
            e = projection.apply(r["embedding"]) if projection else r["embedding"]
            if e is None:
                continue
            sim = max(-1.0, min(1.0, sum(x*y for x, y in zip(q, e))))
            age = now-r["timestamp"]
            decay = math.exp(-math.log(2)*age/half_life)
            w = r["weight"]
            score = sim
            if method != "similarity":
                score *= decay
            if method in ("importance", "protected"):
                score *= w
            if score > threshold:
                out.append({"record": r, "score": score, "explanation": {
                    "similarity": sim, "age_seconds": age,
                    "decay_factor": decay if method != "similarity" else 1,
                    "importance_factor": w if method in ("importance", "protected") else 1,
                    "method": method, "projection_sha256": projection.sha256 if projection else None,
                    "threshold": threshold, "provenance": r["provenance"]}})
        return sorted(out, key=lambda h: (-h["score"], h["record"]["id"]))[:top_k]

    def recall(self, key, query=None, **kwargs):
        """Return exact stored evidence, never a generated completion.

        Any unresolved current contradiction for this key causes UNKNOWN even when
        its low-scoring member would not appear in top-k.
        """
        s = self.snapshot()
        # ATK A8/E1: every current record of the key counts, even one the clock calls "future",
        # and keys compare after NFC normalization, so neither can hide a contradiction.
        current = [r for r in s["records"] if same_key(r["key"], key) and r["status"] == "current"]
        if len({r["value"] for r in current}) > 1:  # MUTATION: contradiction
            return {"status": "UNKNOWN", "reason": "contradictory_current_evidence",
                    "evidence_ids": [r["id"] for r in current]}
        hits = self._retrieve_from(s, query or key, key=key, **kwargs)
        if not hits:
            return {"status": "UNKNOWN", "reason": "insufficient_evidence", "evidence_ids": []}
        return {"status": "KNOWN", "value": hits[0]["record"]["value"],
                "evidence_ids": [h["record"]["id"] for h in hits], "retrieval": hits}
