import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sml.memory import (MemoryStore, CapacityError, IntegrityError, CommitUncertain,
                        canonical, digest, importance, hash_embedding, OrthoProjection, DIM)
from sml.policies import admit


P = {"source": "synthetic-fixture", "locator": "row-1",
     "sha256": hashlib.sha256(b"synthetic-fixture").hexdigest()}


def axis(i):
    return [float(j == i) for j in range(DIM)]


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"store"
        self.time = 1000.0
        self.m = MemoryStore(self.path, create=True, max_records=5,
                             clock=lambda: self.time)

    def tearDown(self):
        self.temp.cleanup()

    def put(self, value="blue", **kwargs):
        return self.m.put("fixture.color", value, provenance=P, **kwargs)

    def test_persistent_exact_fact_and_provenance(self):
        i = self.put(embedding=axis(0))
        m = MemoryStore(self.path, clock=lambda: self.time)
        hit = m.recall("fixture.color", embedding=axis(0))
        self.assertEqual((hit["status"], hit["value"], hit["evidence_ids"]), ("KNOWN", "blue", [i]))
        self.assertEqual(hit["retrieval"][0]["explanation"]["provenance"], P)
        self.assertEqual(m.snapshot()["records"][0]["timestamp"], 1000)

    def test_correct_preserves_protected_original(self):
        old = self.put(protected=True, embedding=axis(0))
        self.time += 1
        new = self.m.correct(old, "green", provenance=P, embedding=axis(0))
        self.assertEqual(self.m.recall("fixture.color", embedding=axis(0))["value"], "green")
        rs = self.m.snapshot()["records"]
        self.assertEqual((rs[0]["status"], rs[0]["protected"], rs[1]["supersedes"]),
                         ("superseded", True, old))
        self.assertEqual([h["record"]["id"] for h in self.m.retrieve("color", embedding=axis(0))], [new])

    def test_revocation_returns_unknown_and_retains_evidence(self):
        i = self.put(protected=True, embedding=axis(0))
        self.m.revoke(i, reason="synthetic correction notice", provenance=P)
        self.assertEqual(self.m.recall("fixture.color", embedding=axis(0))["status"], "UNKNOWN")
        self.assertEqual(self.m.snapshot()["records"][0]["revocation"]["provenance"], P)
        self.assertTrue(self.m.snapshot()["records"][0]["protected"])

    def test_conflict_cannot_be_hidden_below_topk(self):
        self.put("blue", embedding=axis(0))
        self.put("green", embedding=axis(1), weight=0)
        r = self.m.recall("fixture.color", embedding=axis(0), top_k=1)
        self.assertEqual(r["status"], "UNKNOWN")
        self.assertEqual(r["reason"], "contradictory_current_evidence")

    def test_missing_or_unrelated_fact_abstains(self):
        self.put(embedding=axis(1))
        self.assertEqual(self.m.recall("fixture.color", embedding=axis(0))["status"], "UNKNOWN")
        self.assertEqual(self.m.recall("missing")["status"], "UNKNOWN")

    def test_threshold_is_strict(self):
        self.put(embedding=axis(0), weight=.15)
        self.assertEqual(self.m.retrieve("x", embedding=axis(0), method="importance", threshold=.15), [])

    def test_half_life_and_weight_have_explicit_explanation(self):
        self.put(embedding=axis(0), weight=.8)
        self.time += 100
        h = self.m.retrieve("x", embedding=axis(0), half_life=100, method="importance")[0]
        self.assertAlmostEqual(h["score"], .4)
        self.assertAlmostEqual(h["explanation"]["decay_factor"], .5)
        self.assertEqual(h["explanation"]["importance_factor"], .8)

    def test_future_time_and_invalid_numbers_rejected(self):
        before = self.m.path.read_bytes()
        for kwargs in ({"timestamp": 2000}, {"weight": float("nan")},
                       {"weight": True}, {"protected": 1}, {"embedding": axis(0)[:3]}):
            with self.subTest(kwargs=list(kwargs)):
                with self.assertRaises(ValueError):
                    self.put(**kwargs)
        self.assertEqual(before, self.m.path.read_bytes())

    def test_bound_refuses_protected_overflow_without_partial_correction(self):
        for i in range(5):
            self.m.put(f"synthetic.{i}", str(i), provenance=P, protected=True)
        before = self.m.path.read_bytes()
        with self.assertRaises(CapacityError):
            self.put(protected=True)
        with self.assertRaises(CapacityError):
            self.m.correct(1, "changed", provenance=P)
        self.assertEqual(self.m.path.read_bytes(), before)
        self.assertEqual(len(self.m.snapshot()["records"]), 5)

    def test_byte_capacity_includes_text_and_metadata(self):
        before = self.m.path.read_bytes()
        with self.assertRaises(CapacityError):
            self.put("z"*2_000_001)
        self.assertEqual(self.m.path.read_bytes(), before)

    def test_compaction_cannot_drop_protected_chain(self):
        old = self.put(protected=True)
        self.m.correct(old, "green", provenance=P)
        self.m.put("other", "removable", provenance=P, weight=.1)
        before = self.m.path.read_bytes()
        with self.assertRaises(CapacityError):
            self.m.compact(1)
        self.assertEqual(before, self.m.path.read_bytes())
        self.assertEqual(self.m.compact(2), [3])
        self.assertEqual([r["id"] for r in self.m.snapshot()["records"]], [1,2])

    def test_compaction_removes_complete_unprotected_chains(self):
        old = self.put()
        self.m.correct(old, "green", provenance=P)
        self.assertEqual(self.m.compact(0), [1,2])
        self.assertEqual(self.m.recall("fixture.color")["status"], "UNKNOWN")

    def test_corruption_is_not_empty_memory(self):
        self.put()
        self.m.path.write_bytes(b'{"payload":')
        with self.assertRaises(IntegrityError):
            MemoryStore(self.path)
        with self.assertRaises(IntegrityError):
            self.m.recall("fixture.color")

    def test_checksum_detects_valid_json_bit_edit(self):
        self.put()
        env = json.loads(self.m.path.read_bytes())
        env["payload"]["records"][0]["value"] = "evil-edit"
        self.m.path.write_bytes(canonical(env))
        with self.assertRaises(IntegrityError):
            self.m.snapshot()

    def test_semantic_integrity_even_with_recomputed_digest(self):
        self.put()
        for change in ("bad_status", "bad_vector", "orphan", "duplicate"):
            original = self.m.path.read_bytes()
            env = json.loads(original)
            r = env["payload"]["records"][0]
            if change == "bad_status": r["status"] = "imaginary"
            elif change == "bad_vector": r["embedding"] = [0]*384
            elif change == "orphan": r["status"] = "superseded"
            else: env["payload"]["records"].append(copy.deepcopy(r))
            env["sha256"] = digest(env["payload"])
            self.m.path.write_bytes(canonical(env))
            with self.assertRaises(IntegrityError): self.m.snapshot()
            self.m.path.write_bytes(original)

    def test_missing_snapshot_never_reinitialized(self):
        self.m.path.unlink()
        with self.assertRaises(IntegrityError): MemoryStore(self.path)
        with self.assertRaises(FileExistsError): MemoryStore(self.path, create=True)

    def test_duplicate_json_and_nonfinite_payload_rejected(self):
        self.m.path.write_text('{"payload":{},"payload":{},"sha256":"x"}')
        with self.assertRaises(IntegrityError): self.m.snapshot()

    def test_failed_write_does_not_report_success(self):
        self.put()
        before = self.m.path.read_bytes()
        with patch("sml.memory.os.replace", side_effect=OSError("injected disk error")):
            with self.assertRaises(OSError): self.put("green")
        self.assertEqual(before, self.m.path.read_bytes())
        self.assertTrue(self.m.storage_status()["incomplete_storage_detected"])
        self.m.cleanup_incomplete()
        self.assertFalse(self.m.storage_status()["incomplete_storage_detected"])

    def test_post_replace_failure_is_explicitly_uncertain(self):
        self.m.fault = lambda stage: (_ for _ in ()).throw(OSError("injected")) if stage=="after_replace" else None
        with self.assertRaises(CommitUncertain): self.put()
        with self.assertRaises(CommitUncertain): self.m.snapshot()
        reopened = MemoryStore(self.path)
        self.assertEqual(len(reopened.snapshot()["records"]), 1)

    def test_two_handles_reload_before_mutating(self):
        other = MemoryStore(self.path, clock=lambda: self.time)
        self.put()
        other.put("other", "present", provenance=P)
        self.assertEqual(len(self.m.snapshot()["records"]), 2)

    def test_invalid_corrections_are_atomic(self):
        i = self.put()
        self.m.correct(i, "green", provenance=P)
        before = self.m.path.read_bytes()
        with self.assertRaises(ValueError): self.m.correct(i, "red", provenance=P)
        self.assertEqual(before, self.m.path.read_bytes())

    def test_resource_gate_does_not_allow_protected_bypass(self):
        with self.assertRaises(RuntimeError): self.put(protected=True, thermal_state="SCAR_LOCK")
        r = admit(self.m, "protected", "k", "v", provenance=P, force_scar=True, thermal_state="SCAR_LOCK")
        self.assertEqual(r, {"stored": False, "reason": "resource_gate"})
        self.assertEqual(len(self.m.snapshot()["records"]), 0)

    def test_formula_is_recovered_normalized_code_variant(self):
        expected = 1/(1+math.exp(2.15))
        self.assertAlmostEqual(importance(.5,1,1), expected)
        self.assertGreater(importance(1,10,5), .99)
        with self.assertRaises(ValueError): importance(-1,1,1)

    def test_adapters_declare_formation_refusal(self):
        result = admit(self.m, "importance", "k", "v", provenance=P)
        self.assertFalse(result["stored"])
        self.assertEqual(result["reason"], "formation_gate")
        self.assertEqual(len(self.m.snapshot()["records"]), 0)

    def test_hash_is_deterministic_lexical_fallback(self):
        self.assertEqual(hash_embedding("synthetic blue"), hash_embedding("synthetic blue"))
        self.assertAlmostEqual(sum(x*x for x in hash_embedding("synthetic blue")), 1)

    def test_projection_is_optional_and_zero_projection_abstains(self):
        p = OrthoProjection([axis(0)])
        self.put(embedding=axis(1))
        self.assertEqual(self.m.recall("fixture.color", embedding=axis(1), projection=p)["status"], "UNKNOWN")
        with self.assertRaises(ValueError): OrthoProjection([axis(0), axis(0)])
        self.assertEqual(p.apply(axis(0)), axis(0))

    def test_ties_are_reproducible(self):
        self.m.put("k1", "one", provenance=P, embedding=axis(0))
        self.m.put("k2", "two", provenance=P, embedding=axis(0))
        self.assertEqual([h["record"]["id"] for h in self.m.retrieve("x", embedding=axis(0))], [1,2])


if __name__ == "__main__":
    unittest.main()
