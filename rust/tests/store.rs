//! Port-level tests for paths the differential CLI cannot reach (callbacks, faults, odd files),
//! mirroring the Python hardening tests.

use sml::json::Value;
use sml::store::{MemoryStore, PutOptions, Recall, RetrieveOptions, SmlError};
use std::cell::RefCell;
use std::collections::BTreeMap;
use std::fs;
use std::rc::Rc;

fn prov() -> Value {
    let mut m = BTreeMap::new();
    m.insert("source".to_string(), Value::Str("synthetic-rs".into()));
    m.insert("locator".to_string(), Value::Str("rs-1".into()));
    m.insert("sha256".to_string(), Value::Str("a".repeat(64)));
    Value::Obj(m)
}

fn tmp() -> std::path::PathBuf {
    let d = std::env::temp_dir().join(format!("sml-rs-{}-{}", std::process::id(),
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
    fs::create_dir_all(&d).unwrap();
    d.join("s")
}

fn fixed(t: f64) -> Box<dyn Fn() -> f64> {
    Box::new(move || t)
}

#[test]
fn deep_nesting_is_integrity_error() {
    let d = tmp();
    MemoryStore::create(&d, 10, 200_000, fixed(1000.0), None).unwrap();
    let mut b = vec![b'['; 100_000];
    b.extend(vec![b']'; 100_000]);
    fs::write(d.join("memory.json"), b).unwrap();
    assert!(matches!(MemoryStore::open(&d, fixed(1000.0), None), Err(SmlError::Integrity(_))));
}

#[test]
fn lock_path_directory_is_integrity_error() {
    let d = tmp();
    MemoryStore::create(&d, 10, 200_000, fixed(1000.0), None).unwrap();
    fs::remove_file(d.join("memory.lock")).unwrap();
    fs::create_dir(d.join("memory.lock")).unwrap();
    assert!(matches!(MemoryStore::open(&d, fixed(1000.0), None), Err(SmlError::Integrity(_))));
}

#[test]
fn reentrant_clock_is_refused_not_deadlocked() {
    let d = tmp();
    let m = MemoryStore::create(&d, 10, 200_000, fixed(1000.0), None).unwrap();
    let id = m.put("k", "v", &prov(), &PutOptions::default()).unwrap();
    let slot: Rc<RefCell<Option<Rc<MemoryStore>>>> = Rc::new(RefCell::new(None));
    let s2 = slot.clone();
    let clock = Box::new(move || {
        if let Some(st) = s2.borrow().as_ref() {
            let _ = st.snapshot().map_err(|e| assert!(matches!(e, SmlError::Reentrancy(_))));
        }
        1000.0
    });
    let m2 = Rc::new(MemoryStore::open(&d, clock, None).unwrap());
    *slot.borrow_mut() = Some(m2.clone());
    // the nested snapshot is refused inside the callback; revoke itself then completes normally
    m2.revoke(id, "r", &prov()).unwrap();
    *slot.borrow_mut() = None;
}

#[test]
fn fault_before_replace_leaves_state_after_replace_poisons() {
    for (stage, expect_new) in [("partial_write", false), ("after_file_fsync", false), ("after_replace", true),
                                ("after_dir_fsync", true)] {
        let d = tmp();
        MemoryStore::create(&d, 10, 200_000, fixed(1000.0), None).unwrap()
            .put("old", "v", &prov(), &PutOptions::default()).unwrap();
        let st = stage.to_string();
        let fault = Box::new(move |s: &str| if s == st { Err(SmlError::Os("injected".into())) } else { Ok(()) });
        let m = MemoryStore::open(&d, fixed(1000.0), Some(fault)).unwrap();
        let r = m.put("new", "v", &prov(), &PutOptions::default());
        if expect_new {
            assert!(matches!(r, Err(SmlError::CommitUncertain(_))), "{}", stage);
            assert!(matches!(m.snapshot(), Err(SmlError::CommitUncertain(_))));
        } else {
            assert!(matches!(r, Err(SmlError::Os(_))), "{}", stage);
        }
        let n = match MemoryStore::open(&d, fixed(1000.0), None).unwrap().snapshot().unwrap().get("records") {
            Some(Value::Arr(a)) => a.len(),
            _ => 0,
        };
        assert_eq!(n, if expect_new { 2 } else { 1 }, "{}", stage);
    }
}

#[test]
fn clock_behind_record_still_allows_revoke_with_clamped_time() {
    let d = tmp();
    let id = MemoryStore::create(&d, 10, 200_000, fixed(1000.0), None).unwrap()
        .put("k", "v", &prov(), &PutOptions::default()).unwrap();
    MemoryStore::open(&d, fixed(500.0), None).unwrap().revoke(id, "withdraw", &prov()).unwrap();
    let s = MemoryStore::open(&d, fixed(500.0), None).unwrap().snapshot().unwrap();
    let rec = match s.get("records") { Some(Value::Arr(a)) => a[0].clone(), _ => panic!() };
    assert_eq!(rec.get("revocation").unwrap().get("at"), Some(&Value::Float(1000.0)));
}

#[test]
fn nfc_nfd_keys_are_one_key_and_controls_refused() {
    let d = tmp();
    let m = MemoryStore::create(&d, 10, 200_000, fixed(1000.0), None).unwrap();
    m.put("caf\u{e9}", "open", &prov(), &PutOptions::default()).unwrap();
    m.put("cafe\u{301}", "closed", &prov(), &PutOptions::default()).unwrap();
    let o = RetrieveOptions { threshold: 0.0, ..Default::default() };
    assert!(matches!(m.recall("caf\u{e9}", None, &o).unwrap(), Recall::Unknown { reason: "contradictory_current_evidence", .. }));
    for bad in ["a\u{0}b", "\u{202e}evil", "a\u{200b}b", "a\nb"] {
        assert!(matches!(m.put(bad, "v", &prov(), &PutOptions::default()), Err(SmlError::Value(_))));
    }
    assert!(matches!(m.recall("  ", None, &o), Err(SmlError::Value(_))));
}

#[test]
fn capacity_refusals_leave_bytes_unchanged() {
    let d = tmp();
    let m = MemoryStore::create(&d, 2, 200_000, fixed(1000.0), None).unwrap();
    let p = PutOptions { protected: true, ..Default::default() };
    m.put("a", "1", &prov(), &p).unwrap();
    m.put("b", "2", &prov(), &p).unwrap();
    let before = fs::read(d.join("memory.json")).unwrap();
    assert!(matches!(m.put("c", "3", &prov(), &p), Err(SmlError::Capacity(_))));
    assert!(matches!(m.compact(0), Err(SmlError::Capacity(_))));
    assert_eq!(fs::read(d.join("memory.json")).unwrap(), before);
}

#[test]
fn inexact_integer_timestamp_in_file_is_integrity_error() {
    let d = tmp();
    MemoryStore::create(&d, 10, 200_000, fixed(1000.0), None).unwrap()
        .put("k", "v", &prov(), &PutOptions::default()).unwrap();
    let mut s = sml::json::parse(&fs::read(d.join("memory.json")).unwrap()).unwrap().get("payload").unwrap().clone();
    if let Value::Obj(m) = &mut s {
        if let Some(Value::Arr(a)) = m.get_mut("records") {
            if let Value::Obj(r) = &mut a[0] {
                r.insert("timestamp".into(), Value::Int((1i64 << 53) + 1));
                r.insert("recorded_at".into(), Value::Int((1i64 << 53) + 1));
            }
        }
    }
    let digest = sml::text::sha256_hex(&sml::json::canonical(&s).unwrap());
    let mut env = BTreeMap::new();
    env.insert("payload".to_string(), s);
    env.insert("sha256".to_string(), Value::Str(digest));
    let mut b = sml::json::canonical(&Value::Obj(env)).unwrap();
    b.push(b'\n');
    fs::write(d.join("memory.json"), b).unwrap();
    assert!(matches!(MemoryStore::open(&d, fixed(1000.0), None), Err(SmlError::Integrity(_))));
}

#[test]
fn counter_at_i64_max_refuses_write_unchanged() {
    // P3-01: a counter at i64::MAX refuses the write with CapacityError instead of overflowing.
    let d = tmp();
    MemoryStore::create(&d, 10, 200_000, fixed(1000.0), None).unwrap();
    let mut s = sml::json::parse(&fs::read(d.join("memory.json")).unwrap()).unwrap().get("payload").unwrap().clone();
    if let Value::Obj(m) = &mut s {
        m.insert("next_id".into(), Value::Int(i64::MAX));
    }
    let digest = sml::text::sha256_hex(&sml::json::canonical(&s).unwrap());
    let mut env = BTreeMap::new();
    env.insert("payload".to_string(), s);
    env.insert("sha256".to_string(), Value::Str(digest));
    let mut b = sml::json::canonical(&Value::Obj(env)).unwrap();
    b.push(b'\n');
    fs::write(d.join("memory.json"), &b).unwrap();
    let m = MemoryStore::open(&d, fixed(1000.0), None).unwrap();
    assert!(matches!(m.put("k", "v", &prov(), &PutOptions::default()), Err(SmlError::Capacity(_))));
    assert_eq!(fs::read(d.join("memory.json")).unwrap(), b);
}
