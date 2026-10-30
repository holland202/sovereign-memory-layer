//! Rust port of `sml/memory.py` (the Python reference). Same on-disk format, same checks, same
//! error classes. POSIX local filesystems, cooperative writers only. Checksums detect accidental
//! corruption, not malicious rewriting or rollback. Scores are retrieval heuristics.
//!
//! Not ported: `OrthoProjection` and `policies.admit`.

use crate::json::{self, Value};
use crate::text::{self, py_sum, DIM};
use std::cell::Cell;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::io::AsRawFd;
use std::path::{Path, PathBuf};

pub const READ_LIMIT: usize = 16_000_000;
pub const METHODS: [&str; 4] = ["similarity", "recency", "importance", "protected"];
const RECORD_FIELDS: [&str; 13] = ["id", "key", "value", "text", "provenance", "timestamp", "recorded_at", "weight",
                                   "protected", "status", "supersedes", "revocation", "embedding"];

#[derive(Debug, Clone, PartialEq)]
pub enum SmlError {
    /// Python ValueError: invalid argument; nothing written.
    Value(String),
    /// No mutation committed: protected records are never silently discarded.
    Capacity(String),
    /// Unreadable or invalid state; no empty-store fallback.
    Integrity(String),
    /// Replace occurred but durability confirmation failed; reopen before retry.
    CommitUncertain(String),
    /// A store call made from inside another call on the same store (from clock() or fault()).
    Reentrancy(String),
    /// Python RuntimeError (the SCAR_LOCK resource gate).
    Runtime(String),
    /// Python OSError (filesystem error outside the load path).
    Os(String),
}

impl SmlError {
    pub fn class(&self) -> &'static str {
        match self {
            SmlError::Value(_) => "ValueError",
            SmlError::Capacity(_) => "CapacityError",
            SmlError::Integrity(_) => "IntegrityError",
            SmlError::CommitUncertain(_) => "CommitUncertain",
            SmlError::Reentrancy(_) => "ReentrancyError",
            SmlError::Runtime(_) => "RuntimeError",
            SmlError::Os(_) => "OSError",
        }
    }
}

impl std::fmt::Display for SmlError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let m = match self {
            SmlError::Value(m) | SmlError::Capacity(m) | SmlError::Integrity(m) | SmlError::CommitUncertain(m)
            | SmlError::Reentrancy(m) | SmlError::Runtime(m) | SmlError::Os(m) => m,
        };
        write!(f, "{}: {}", self.class(), m)
    }
}

impl std::error::Error for SmlError {}

pub type Result<T> = std::result::Result<T, SmlError>;

fn verr<T>(m: &str) -> Result<T> {
    Err(SmlError::Value(m.to_string()))
}

fn os(e: std::io::Error) -> SmlError {
    SmlError::Os(e.to_string())
}

// ------------------------------------------------------------------ validation helpers

/// Python `number(x, name, low, high)`; returns float(x).
pub fn number(x: &Value, name: &str, low: f64, high: f64) -> Result<f64> {
    if let Value::Int(i) = x {
        // R3-02: refuse an integer f64 cannot hold exactly, as the Python reference does.
        if ((*i as f64) as i128) != (*i as i128) {
            return verr(&format!("invalid {}", name));
        }
    }
    match x.as_number() {
        Some(f) if f.is_finite() && low <= f && f <= high => Ok(f),
        _ => verr(&format!("invalid {}", name)),
    }
}

fn number_f(x: f64, name: &str, low: f64, high: f64) -> Result<f64> {
    number(&Value::Float(x), name, low, high)
}

fn nonempty<'a>(x: &'a Value, name: &str) -> Result<&'a str> {
    match x.as_str() {
        Some(s) if !text::py_blank(s) => Ok(s),
        _ => verr(&format!("empty {}", name)),
    }
}

fn nonempty_s<'a>(s: &'a str, name: &str) -> Result<&'a str> {
    if text::py_blank(s) {
        return verr(&format!("empty {}", name));
    }
    Ok(s)
}

/// Keys and provenance identifiers: NFC-normalized, no control/format characters.
pub fn identifier(s: &str, name: &str) -> Result<String> {
    nonempty_s(s, name)?;
    if text::has_control_or_format(s) {
        return verr(&format!("{} contains control, format or surrogate characters", name));
    }
    Ok(text::nfc(s))
}

pub fn same_key(a: &Value, b: &str) -> bool {
    matches!(a, Value::Str(s) if text::nfc(s) == text::nfc(b))
}

fn validate_provenance(p: &Value) -> Result<Value> {
    let m = match p.as_obj() {
        Some(m) if m.keys().map(String::as_str).collect::<BTreeSet<_>>()
            == ["locator", "sha256", "source"].into_iter().collect() => m,
        _ => return verr("provenance requires source, locator, sha256"),
    };
    nonempty(&m["source"], "source")?;
    nonempty(&m["locator"], "locator")?;
    match m["sha256"].as_str() {
        Some(h) if h.len() == 64 && h.chars().all(|c| "0123456789abcdef".contains(c)) => {}
        _ => return verr("invalid source digest"),
    }
    Ok(p.clone())
}

/// Provenance supplied by a caller now (put and revoke).
fn new_provenance(p: &Value) -> Result<Value> {
    let p = validate_provenance(p)?;
    identifier(p.get("source").and_then(Value::as_str).unwrap_or(""), "source")?;
    identifier(p.get("locator").and_then(Value::as_str).unwrap_or(""), "locator")?;
    Ok(p)
}

/// Python `vector(xs)`: DIM finite numbers within ±1e100, normalized.
pub fn vector_of(xs: &Value) -> Result<Vec<f64>> {
    let a = match xs {
        Value::Arr(a) if a.len() == DIM => a,
        _ => return verr("embedding dimension mismatch"),
    };
    let v: Vec<f64> = a.iter().map(|x| number(x, "embedding", -1e100, 1e100)).collect::<Result<_>>()?;
    normalize(v)
}

pub fn vector(v: &[f64]) -> Result<Vec<f64>> {
    if v.len() != DIM {
        return verr("embedding dimension mismatch");
    }
    let v: Vec<f64> = v.iter().map(|x| number_f(*x, "embedding", -1e100, 1e100)).collect::<Result<_>>()?;
    normalize(v)
}

fn normalize(v: Vec<f64>) -> Result<Vec<f64>> {
    let norm = py_sum(v.iter().map(|x| x * x)).sqrt();
    if norm == 0.0 {
        return verr("zero embedding");
    }
    Ok(v.iter().map(|x| x / norm).collect())
}

pub fn hash_embedding(t: &str) -> Result<Vec<f64>> {
    nonempty_s(t, "text")?;
    vector(&text::hash_embedding_raw(t))
}

/// Recovered core.py importance formula (sigmoid of a normalized weighted sum).
pub fn importance(governance: f64, entropy: f64, residual: f64) -> Result<f64> {
    let g = number_f(governance, "governance", 0.0, 1.0)?;
    let h = number_f(entropy, "entropy", 0.0, f64::INFINITY)?;
    let r = number_f(residual, "residual", 0.0, f64::INFINITY)?;
    let raw = 0.40 * g + 0.35 * (h / 10.0).min(1.0) + 0.25 * (r / 5.0).min(1.0);
    Ok(1.0 / (1.0 + (-10.0 * (raw - 0.5)).exp()))
}

fn digest(v: &Value) -> std::result::Result<String, String> {
    Ok(text::sha256_hex(&json::canonical(v)?))
}

fn encode(state: &Value) -> Result<Vec<u8>> {
    let d = digest(state).map_err(SmlError::Value)?;
    let mut env = BTreeMap::new();
    env.insert("payload".to_string(), state.clone());
    env.insert("sha256".to_string(), Value::Str(d));
    let mut b = json::canonical(&Value::Obj(env)).map_err(SmlError::Value)?;
    b.push(b'\n');
    Ok(b)
}

fn int_of(v: &Value) -> Option<i64> {
    if let Value::Int(i) = v { Some(*i) } else { None }
}

fn validate(s: &Value) -> Result<()> {
    let m = match s.as_obj() {
        Some(m) if m.keys().map(String::as_str).collect::<BTreeSet<_>>()
            == ["generation", "max_bytes", "max_records", "next_id", "records", "schema"].into_iter().collect()
            && m["schema"] == Value::Int(1) => m,
        _ => return verr("invalid snapshot schema"),
    };
    for k in ["generation", "next_id", "max_records", "max_bytes"] {
        match int_of(&m[k]) {
            Some(i) if i >= if k == "generation" { 0 } else { 1 } => {}
            _ => return verr("invalid snapshot counters"),
        }
    }
    let max_bytes = int_of(&m["max_bytes"]).unwrap();
    if !(1024..=READ_LIMIT as i64).contains(&max_bytes) {
        return verr("stored max_bytes outside supported range");
    }
    let next_id = int_of(&m["next_id"]).unwrap();
    let records = match &m["records"] {
        Value::Arr(a) if a.len() as i64 <= int_of(&m["max_records"]).unwrap() => a,
        _ => return verr("record bound violated"),
    };
    let mut ids = HashSet::new();
    let mut by_id: BTreeMap<i64, &BTreeMap<String, Value>> = BTreeMap::new();
    let fields: BTreeSet<&str> = RECORD_FIELDS.into_iter().collect();
    for r in records {
        let r = match r.as_obj() {
            Some(o) if o.keys().map(String::as_str).collect::<BTreeSet<_>>() == fields => o,
            _ => return verr("invalid record schema"),
        };
        let i = match int_of(&r["id"]) {
            Some(i) if 0 < i && i < next_id && !ids.contains(&i) => i,
            _ => return verr("invalid or duplicate id"),
        };
        ids.insert(i);
        by_id.insert(i, r);
        for k in ["key", "value", "text"] {
            nonempty(&r[k], k)?;
        }
        validate_provenance(&r["provenance"])?;
        let t = number(&r["timestamp"], "timestamp", 0.0, f64::INFINITY)?;
        number(&r["recorded_at"], "recorded_at", t, f64::INFINITY)?;
        number(&r["weight"], "weight", 0.0, 1.0)?;
        let status = r["status"].as_str().unwrap_or("");
        if !matches!(r["protected"], Value::Bool(_)) || !["current", "superseded", "revoked"].contains(&status) {
            return verr("invalid record status");
        }
        vector_of(&r["embedding"])?;
        if let Value::Arr(e) = &r["embedding"] {
            let ss = py_sum(e.iter().map(|x| { let f = x.as_number().unwrap(); f * f }));
            if (ss - 1.0).abs() > 1e-8 {
                return verr("unnormalized embedding");
            }
        }
        match &r["supersedes"] {
            Value::Null => {}
            Value::Int(t) if *t < i => {}
            _ => return verr("invalid correction link"),
        }
        let rev = &r["revocation"];
        if status == "revoked" {
            match rev.as_obj() {
                Some(o) if o.keys().map(String::as_str).collect::<BTreeSet<_>>()
                    == ["at", "provenance", "reason"].into_iter().collect() => {
                    nonempty(&o["reason"], "reason")?;
                    validate_provenance(&o["provenance"])?;
                    number(&o["at"], "revocation time", t, f64::INFINITY)?;
                }
                _ => return verr("invalid revocation"),
            }
        } else if *rev != Value::Null {
            return verr("unexpected revocation");
        }
    }
    let mut referenced = HashSet::new();
    for r in records {
        let r = r.as_obj().unwrap();
        if let Value::Int(target) = r["supersedes"] {
            let key = r["key"].as_str().unwrap();
            let ok = by_id.get(&target).map_or(false, |t| same_key(&t["key"], key)) && !referenced.contains(&target);
            if !ok {
                return verr("missing, cross-key, or forked correction");
            }
            let t = by_id[&target];
            if t["status"].as_str() != Some("superseded")
                || t["timestamp"].as_number().unwrap() > r["timestamp"].as_number().unwrap() {
                return verr("invalid supersession");
            }
            referenced.insert(target);
        }
    }
    for r in records {
        let r = r.as_obj().unwrap();
        if r["status"].as_str() == Some("superseded") && !referenced.contains(&int_of(&r["id"]).unwrap()) {
            return verr("orphan supersession");
        }
    }
    if encode(s)?.len() as i64 > max_bytes {
        return verr("byte bound violated");
    }
    Ok(())
}

// ------------------------------------------------------------------ the store

thread_local! {
    static HELD: std::cell::RefCell<HashSet<PathBuf>> = std::cell::RefCell::new(HashSet::new());
}

pub type Clock = Box<dyn Fn() -> f64>;
pub type Fault = Box<dyn Fn(&str) -> std::result::Result<(), SmlError>>;

#[derive(Default, Clone)]
pub struct PutOptions {
    pub timestamp: Option<f64>,
    pub text: Option<String>,
    pub weight: Option<f64>,
    pub protected: bool,
    pub supersedes: Option<i64>,
    pub embedding: Option<Vec<f64>>,
    pub thermal_state: Option<String>,
}

#[derive(Clone)]
pub struct RetrieveOptions {
    pub method: String,
    pub top_k: i64,
    pub threshold: f64,
    pub half_life: f64,
    pub key: Option<String>,
    pub embedding: Option<Vec<f64>>,
}

impl Default for RetrieveOptions {
    fn default() -> Self {
        RetrieveOptions { method: "similarity".into(), top_k: 5, threshold: 0.15, half_life: 30.0 * 86400.0,
                          key: None, embedding: None }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Hit {
    pub record: Value,
    pub score: f64,
    pub similarity: f64,
    pub decay: f64,
    pub importance: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Recall {
    Known { value: String, evidence_ids: Vec<i64>, retrieval: Vec<Hit> },
    Unknown { reason: &'static str, evidence_ids: Vec<i64> },
}

#[derive(Debug, Clone, PartialEq)]
pub struct StorageStatus {
    pub generation: i64,
    pub records: usize,
    pub bytes: u64,
    pub max_records: i64,
    pub max_bytes: i64,
    pub incomplete_storage_detected: bool,
}

pub struct MemoryStore {
    pub directory: PathBuf,
    pub path: PathBuf,
    pub pending: PathBuf,
    clock: Clock,
    fault: Fault,
    poisoned: Cell<bool>,
}

struct LockGuard {
    file: File,
    me: PathBuf,
}

impl Drop for LockGuard {
    fn drop(&mut self) {
        HELD.with(|h| h.borrow_mut().remove(&self.me));
        unsafe {
            libc::flock(self.file.as_raw_fd(), libc::LOCK_UN);
        }
    }
}

fn realpath(p: &Path) -> PathBuf {
    fs::canonicalize(p).unwrap_or_else(|_| std::env::current_dir().map(|d| d.join(p)).unwrap_or_else(|_| p.into()))
}

fn rec(s: &mut Value) -> &mut Vec<Value> {
    if let Value::Obj(m) = s {
        if let Some(Value::Arr(a)) = m.get_mut("records") {
            return a;
        }
    }
    unreachable!("validated snapshot")
}

/// P3-01: a counter at i64::MAX refuses the write (CapacityError), as Python's `_bump` does.
fn bump(s: &mut Value, k: &str) -> Result<()> {
    if let Value::Obj(m) = s {
        if let Some(Value::Int(i)) = m.get_mut(k) {
            *i = i.checked_add(1).ok_or_else(|| SmlError::Capacity(format!("{} exhausted; no write committed", k)))?;
        }
    }
    Ok(())
}

fn field(s: &Value, k: &str) -> i64 {
    int_of(s.get(k).unwrap()).unwrap()
}

fn set(r: &mut Value, k: &str, v: Value) {
    if let Value::Obj(m) = r {
        m.insert(k.to_string(), v);
    }
}

impl MemoryStore {
    /// Python `MemoryStore(directory, create=True, ...)`: refuses an existing directory.
    pub fn create(directory: impl AsRef<Path>, max_records: i64, max_bytes: i64, clock: Clock, fault: Option<Fault>)
                  -> Result<Self> {
        if max_records < 1 {
            return verr("invalid max_records");
        }
        if !(1024..=16_000_000).contains(&max_bytes) {
            return verr("invalid max_bytes");
        }
        let st = Self::new(directory.as_ref(), clock, fault);
        fs::DirBuilder::new().mode(0o700).create(&st.directory).map_err(os)?;
        {
            let _g = st.lock()?;
            let mut m = BTreeMap::new();
            m.insert("schema".into(), Value::Int(1));
            m.insert("generation".into(), Value::Int(0));
            m.insert("next_id".into(), Value::Int(1));
            m.insert("max_records".into(), Value::Int(max_records));
            m.insert("max_bytes".into(), Value::Int(max_bytes));
            m.insert("records".into(), Value::Arr(vec![]));
            st.commit(&Value::Obj(m))?;
        }
        {
            let _g = st.lock()?;
            st.load()?;
        }
        Ok(st)
    }

    /// Python `MemoryStore(directory)`: opens an existing store or fails.
    pub fn open(directory: impl AsRef<Path>, clock: Clock, fault: Option<Fault>) -> Result<Self> {
        let st = Self::new(directory.as_ref(), clock, fault);
        if !st.directory.is_dir() {
            return Err(SmlError::Integrity("store does not exist; explicit create required".into()));
        }
        {
            let _g = st.lock()?;
            st.load()?;
        }
        Ok(st)
    }

    fn new(directory: &Path, clock: Clock, fault: Option<Fault>) -> Self {
        let d = directory.to_path_buf();
        MemoryStore { path: d.join("memory.json"), pending: d.join("memory.pending"), directory: d, clock,
                      fault: fault.unwrap_or_else(|| Box::new(|_| Ok(()))), poisoned: Cell::new(false) }
    }

    fn now(&self) -> Result<f64> {
        number_f((self.clock)(), "clock", 0.0, f64::INFINITY)
    }

    fn lock(&self) -> Result<LockGuard> {
        if self.poisoned.get() {
            return Err(SmlError::CommitUncertain("reopen store before further use".into()));
        }
        let me = realpath(&self.directory);
        if HELD.with(|h| h.borrow().contains(&me)) {
            return Err(SmlError::Reentrancy("store called re-entrantly (e.g. from clock() or fault()); refused".into()));
        }
        let file = OpenOptions::new().read(true).append(true).create(true).open(self.directory.join("memory.lock"))
            .map_err(|e| SmlError::Integrity(format!("cannot open lock file: {}", e)))?;
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) } != 0 {
            // EXT-01 N3: same class as an unopenable lock file (Python LockError, an IntegrityError).
            return Err(SmlError::Integrity(format!("cannot lock store: {}", std::io::Error::last_os_error())));
        }
        HELD.with(|h| h.borrow_mut().insert(me.clone()));
        Ok(LockGuard { file, me })
    }

    fn load(&self) -> Result<Value> {
        let integrity = |m: String| SmlError::Integrity(m);
        let meta = fs::metadata(&self.path).map_err(|e| integrity(e.to_string()))?;
        if meta.len() > READ_LIMIT as u64 {
            return Err(integrity("snapshot exceeds reader hard limit".into()));
        }
        let bytes = fs::read(&self.path).map_err(|e| integrity(e.to_string()))?;
        let env = json::parse(&bytes).map_err(integrity)?;
        let m = match env.as_obj() {
            Some(m) if m.len() == 2 && m.contains_key("payload") && m.contains_key("sha256") => m,
            _ => return Err(integrity("invalid envelope".into())),
        };
        let s = m["payload"].clone();
        let d = digest(&s).map_err(integrity)?;
        if m["sha256"].as_str() != Some(d.as_str()) {
            return Err(integrity("checksum mismatch".into()));
        }
        validate(&s).map_err(|e| integrity(e.to_string()))?;
        Ok(s)
    }

    fn commit(&self, state: &Value) -> Result<()> {
        validate(state)?;
        let data = encode(state)?;
        if data.len() > READ_LIMIT {
            return Err(SmlError::Capacity("snapshot would exceed the reader limit; no write committed".into()));
        }
        let mut replaced = false;
        let r: Result<()> = (|| {
            {
                let mut h = File::create(&self.pending).map_err(os)?;
                fs::set_permissions(&self.pending, fs::Permissions::from_mode(0o600)).map_err(os)?;
                h.write_all(&data[..data.len() / 2]).map_err(os)?;
                h.flush().map_err(os)?;
                (self.fault)("partial_write")?;
                h.write_all(&data[data.len() / 2..]).map_err(os)?;
                h.flush().map_err(os)?;
                h.sync_all().map_err(os)?;
            }
            (self.fault)("after_file_fsync")?;
            fs::rename(&self.pending, &self.path).map_err(os)?;
            replaced = true;
            (self.fault)("after_replace")?;
            let d = OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY).open(&self.directory).map_err(os)?;
            d.sync_all().map_err(os)?;
            (self.fault)("after_dir_fsync")?;
            Ok(())
        })();
        match r {
            Err(e) if replaced => {
                self.poisoned.set(true);
                Err(SmlError::CommitUncertain(format!("replaced but acknowledgement failed: {}", e)))
            }
            other => other,
        }
    }

    pub fn snapshot(&self) -> Result<Value> {
        let _g = self.lock()?;
        self.load()
    }

    pub fn storage_status(&self) -> Result<StorageStatus> {
        let _g = self.lock()?;
        let s = self.load()?;
        Ok(StorageStatus {
            generation: field(&s, "generation"),
            records: if let Some(Value::Arr(a)) = s.get("records") { a.len() } else { 0 },
            bytes: fs::metadata(&self.path).map_err(os)?.len(),
            max_records: field(&s, "max_records"),
            max_bytes: field(&s, "max_bytes"),
            incomplete_storage_detected: self.pending.exists(),
        })
    }

    pub fn cleanup_incomplete(&self) -> Result<()> {
        let _g = self.lock()?;
        self.load()?;
        match fs::remove_file(&self.pending) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(os(e)),
            _ => Ok(()),
        }
    }

    pub fn put(&self, key: &str, value: &str, provenance: &Value, o: &PutOptions) -> Result<i64> {
        match o.thermal_state.as_deref().unwrap_or("NOMINAL") {
            "NOMINAL" | "THROTTLE" => {}
            "SCAR_LOCK" => return Err(SmlError::Runtime("resource gate closed, including protected writes".into())),
            _ => return verr("unknown resource state"),
        }
        let key = identifier(key, "key")?;
        nonempty_s(value, "value")?;
        let p = new_provenance(provenance)?;
        let w = number_f(o.weight.unwrap_or(1.0), "weight", 0.0, 1.0)?;
        let now = self.now()?;
        let ts = match o.timestamp {
            None => now,
            Some(t) => number_f(t, "timestamp", 0.0, now)?,
        };
        let txt = o.text.clone().unwrap_or_else(|| format!("{} {}", key, value));
        nonempty_s(&txt, "text")?;
        // EXT-01 N1: refuse a write that cannot fit before the embedding work, with the cheap checks in
        // the same order as the locked section below (same refusal reasons as the Python reference).
        let supplied = match &o.embedding {
            None => None,
            Some(e) => Some(vector(e)?),
        };
        let floor = (key.chars().count() + value.chars().count() + txt.chars().count()) as i64;
        if floor > READ_LIMIT as i64 {
            return Err(SmlError::Capacity("record cannot fit in any store; no write committed".into()));
        }
        {
            let _g = self.lock()?;
            let mut s = self.load()?;
            if rec(&mut s).len() as i64 >= field(&s, "max_records") {
                return Err(SmlError::Capacity("record capacity exhausted; no write committed".into()));
            }
            if let Some(sup) = o.supersedes {
                let old = match rec(&mut s).iter().find(|r| int_of(r.get("id").unwrap()) == Some(sup)) {
                    Some(r) => r.clone(),
                    None => return verr("unknown correction target"),
                };
                if old.get("status").and_then(Value::as_str) != Some("current") || !same_key(old.get("key").unwrap(), &key)
                    || old.get("timestamp").unwrap().as_number().unwrap() > ts {
                    return verr("correction requires current same-key predecessor");
                }
            }
            if encode(&s)?.len() as i64 + floor > field(&s, "max_bytes") {
                return Err(SmlError::Capacity("byte capacity exhausted; no write committed".into()));
            }
        }
        let emb = match supplied {
            Some(e) => e,
            None => hash_embedding(&txt)?,
        };
        let _g = self.lock()?;
        let mut s = self.load()?;
        if rec(&mut s).len() as i64 >= field(&s, "max_records") {
            return Err(SmlError::Capacity("record capacity exhausted; no write committed".into()));
        }
        if let Some(sup) = o.supersedes {
            let records = rec(&mut s);
            let old = match records.iter_mut().find(|r| int_of(r.get("id").unwrap()) == Some(sup)) {
                Some(r) => r,
                None => return verr("unknown correction target"),
            };
            if old.get("status").and_then(Value::as_str) != Some("current") || !same_key(old.get("key").unwrap(), &key)
                || old.get("timestamp").unwrap().as_number().unwrap() > ts {
                return verr("correction requires current same-key predecessor");
            }
            set(old, "status", Value::Str("superseded".into()));
        }
        let i = field(&s, "next_id");
        let mut r = BTreeMap::new();
        r.insert("id".into(), Value::Int(i));
        r.insert("key".into(), Value::Str(key));
        r.insert("value".into(), Value::Str(value.to_string()));
        r.insert("text".into(), Value::Str(txt));
        r.insert("provenance".into(), p);
        r.insert("timestamp".into(), Value::Float(ts));
        r.insert("recorded_at".into(), Value::Float(now));
        r.insert("weight".into(), Value::Float(w));
        r.insert("protected".into(), Value::Bool(o.protected));
        r.insert("status".into(), Value::Str("current".into()));
        r.insert("supersedes".into(), o.supersedes.map_or(Value::Null, Value::Int));
        r.insert("revocation".into(), Value::Null);
        r.insert("embedding".into(), Value::Arr(emb.into_iter().map(Value::Float).collect()));
        rec(&mut s).push(Value::Obj(r));
        bump(&mut s, "next_id")?;
        bump(&mut s, "generation")?;
        if encode(&s)?.len() as i64 > field(&s, "max_bytes") {
            return Err(SmlError::Capacity("byte capacity exhausted; no write committed".into()));
        }
        self.commit(&s)?;
        Ok(i)
    }

    pub fn correct(&self, record_id: i64, value: &str, provenance: &Value, o: &PutOptions) -> Result<i64> {
        if record_id < 1 {
            return verr("positive integer record ID required");
        }
        let s = self.snapshot()?;
        let key = match s.get("records") {
            Some(Value::Arr(a)) => a.iter().find(|r| int_of(r.get("id").unwrap()) == Some(record_id))
                .and_then(|r| r.get("key")).and_then(Value::as_str).map(String::from),
            _ => None,
        };
        let key = match key {
            Some(k) => k,
            None => return verr("unknown correction target"),
        };
        let mut o = o.clone();
        o.supersedes = Some(record_id);
        self.put(&key, value, provenance, &o)
    }

    pub fn revoke(&self, record_id: i64, reason: &str, provenance: &Value) -> Result<()> {
        if record_id < 1 {
            return verr("positive integer record ID required");
        }
        nonempty_s(reason, "reason")?;
        let p = new_provenance(provenance)?;
        let _g = self.lock()?;
        let mut s = self.load()?;
        let now = self.now()?;
        {
            let records = rec(&mut s);
            let r = match records.iter_mut().find(|r| int_of(r.get("id").unwrap()) == Some(record_id)) {
                Some(r) if r.get("status").and_then(Value::as_str) == Some("current") => r,
                _ => return verr("revocation requires a current record"),
            };
            set(r, "status", Value::Str("revoked".into()));
            // A clock behind the record's timestamp must not block withdrawal (clamped, as in Python's max()).
            let ts = r.get("timestamp").unwrap().clone();
            let at = if ts.as_number().unwrap() > now { ts } else { Value::Float(now) };
            let mut rv = BTreeMap::new();
            rv.insert("reason".into(), Value::Str(reason.to_string()));
            rv.insert("provenance".into(), p);
            rv.insert("at".into(), at);
            set(r, "revocation", Value::Obj(rv));
        }
        bump(&mut s, "generation")?;
        if encode(&s)?.len() as i64 > field(&s, "max_bytes") {
            return Err(SmlError::Capacity("revocation does not fit; original unchanged".into()));
        }
        self.commit(&s)
    }

    pub fn compact(&self, target_records: i64) -> Result<Vec<i64>> {
        if target_records < 0 {
            return verr("invalid target_records");
        }
        let _g = self.lock()?;
        let mut s = self.load()?;
        let records = rec(&mut s).clone();
        let mut sorted: Vec<&Value> = records.iter().collect();
        sorted.sort_by_key(|r| int_of(r.get("id").unwrap()).unwrap());
        let mut roots: BTreeMap<i64, i64> = BTreeMap::new();
        let mut order: Vec<i64> = vec![];
        let mut groups: BTreeMap<i64, Vec<&Value>> = BTreeMap::new();
        for r in sorted {
            let id = int_of(r.get("id").unwrap()).unwrap();
            let root = match r.get("supersedes").unwrap() {
                Value::Int(t) => roots[t],
                _ => id,
            };
            roots.insert(id, root);
            if !groups.contains_key(&root) {
                order.push(root);
            }
            groups.entry(root).or_default().push(r);
        }
        let mut removable: Vec<&Vec<&Value>> = order.iter().map(|k| &groups[k])
            .filter(|g| !g.iter().any(|r| r.get("protected") == Some(&Value::Bool(true)))).collect();
        let wmax = |g: &Vec<&Value>| g.iter().map(|r| r.get("weight").unwrap().as_number().unwrap()).fold(f64::NEG_INFINITY, f64::max);
        removable.sort_by(|a, b| wmax(a).partial_cmp(&wmax(b)).unwrap()
            .then(int_of(a[0].get("id").unwrap()).cmp(&int_of(b[0].get("id").unwrap()))));
        let mut removed: Vec<i64> = vec![];
        let mut count = records.len() as i64;
        for g in removable {
            if count <= target_records {
                break;
            }
            removed.extend(g.iter().map(|r| int_of(r.get("id").unwrap()).unwrap()));
            count -= g.len() as i64;
        }
        if count > target_records {
            return Err(SmlError::Capacity("protected chains prevent compaction; unchanged".into()));
        }
        if !removed.is_empty() {
            let keep: Vec<Value> = records.into_iter()
                .filter(|r| !removed.contains(&int_of(r.get("id").unwrap()).unwrap())).collect();
            *rec(&mut s) = keep;
            bump(&mut s, "generation")?;
            self.commit(&s)?;
        }
        Ok(removed)
    }

    pub fn retrieve(&self, query: &str, o: &RetrieveOptions) -> Result<Vec<Hit>> {
        let s = self.snapshot()?;
        self.retrieve_from(&s, query, o)
    }

    fn retrieve_from(&self, s: &Value, query: &str, o: &RetrieveOptions) -> Result<Vec<Hit>> {
        if !METHODS.contains(&o.method.as_str()) {
            return verr("unknown retrieval method");
        }
        if !(1..=100).contains(&o.top_k) {
            return verr("invalid top_k");
        }
        let threshold = number_f(o.threshold, "threshold", 0.0, 1.0)?;
        let half_life = number_f(o.half_life, "half_life", 1e-9, f64::INFINITY)?;
        let now = self.now()?;
        let q = match &o.embedding {
            None => hash_embedding(query)?,
            Some(e) => vector(e)?,
        };
        let mut out = vec![];
        if let Some(Value::Arr(records)) = s.get("records") {
            for r in records {
                if r.get("status").and_then(Value::as_str) != Some("current") {
                    continue;
                }
                if let Some(k) = &o.key {
                    if !same_key(r.get("key").unwrap(), k) {
                        continue;
                    }
                }
                let ts = r.get("timestamp").unwrap().as_number().unwrap();
                if ts > now {
                    continue;
                }
                let e: Vec<f64> = match r.get("embedding") {
                    Some(Value::Arr(a)) => a.iter().map(|x| x.as_number().unwrap()).collect(),
                    _ => continue,
                };
                let sim = py_sum(q.iter().zip(e.iter()).map(|(x, y)| x * y)).clamp(-1.0, 1.0);
                let age = now - ts;
                let decay = (-(2.0f64).ln() * age / half_life).exp();
                let w = r.get("weight").unwrap().as_number().unwrap();
                let mut score = sim;
                if o.method != "similarity" {
                    score *= decay;
                }
                if o.method == "importance" || o.method == "protected" {
                    score *= w;
                }
                if score > threshold {
                    out.push(Hit { record: r.clone(), score, similarity: sim,
                                   decay: if o.method != "similarity" { decay } else { 1.0 },
                                   importance: if o.method == "importance" || o.method == "protected" { w } else { 1.0 } });
                }
            }
        }
        out.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap()
            .then(int_of(a.record.get("id").unwrap()).cmp(&int_of(b.record.get("id").unwrap()))));
        out.truncate(o.top_k as usize);
        Ok(out)
    }

    /// Exact stored evidence or UNKNOWN; never a generated completion.
    pub fn recall(&self, key: &str, query: Option<&str>, o: &RetrieveOptions) -> Result<Recall> {
        if key.trim_matches(text::py_isspace).is_empty() {
            return verr("recall requires a non-empty string key");
        }
        let s = self.snapshot()?;
        let current: Vec<&Value> = match s.get("records") {
            Some(Value::Arr(a)) => a.iter().filter(|r| same_key(r.get("key").unwrap(), key)
                && r.get("status").and_then(Value::as_str) == Some("current")).collect(),
            _ => vec![],
        };
        let values: BTreeSet<&str> = current.iter().filter_map(|r| r.get("value").and_then(Value::as_str)).collect();
        if values.len() > 1 {
            return Ok(Recall::Unknown { reason: "contradictory_current_evidence",
                evidence_ids: current.iter().map(|r| int_of(r.get("id").unwrap()).unwrap()).collect() });
        }
        let mut o = o.clone();
        o.key = Some(key.to_string());
        let q = match query {
            Some(q) if !q.is_empty() => q,
            _ => key,
        };
        let hits = self.retrieve_from(&s, q, &o)?;
        if hits.is_empty() {
            return Ok(Recall::Unknown { reason: "insufficient_evidence", evidence_ids: vec![] });
        }
        Ok(Recall::Known {
            value: hits[0].record.get("value").and_then(Value::as_str).unwrap_or("").to_string(),
            evidence_ids: hits.iter().map(|h| int_of(h.record.get("id").unwrap()).unwrap()).collect(),
            retrieval: hits,
        })
    }
}
