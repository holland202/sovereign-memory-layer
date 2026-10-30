//! Line protocol used by the differential tests (`tools/differential.py`). One JSON object per
//! line on stdin; one canonical JSON result per line on stdout. Every operation reopens the
//! store, with the clock fixed to the operation's "clock" value. Mirrors `tools/py_cli.py`.

use sml::json::{self, py_float_repr, Value};
use sml::store::{Hit, MemoryStore, PutOptions, Recall, RetrieveOptions, SmlError};
use std::collections::BTreeMap;
use std::io::{BufRead, Write};

fn obj(pairs: Vec<(&str, Value)>) -> Value {
    Value::Obj(pairs.into_iter().map(|(k, v)| (k.to_string(), v)).collect::<BTreeMap<_, _>>())
}

fn bad(k: &str) -> SmlError {
    SmlError::Value(format!("invalid {}", k))
}

/// A number option, typed exactly as the Python reference treats it (R3-03): absent or null is
/// "not given"; a float or an exactly representable integer is the value; anything else is the
/// ValueError Python's number() would raise.
fn num(op: &Value, k: &str) -> Result<Option<f64>, SmlError> {
    match op.get(k) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Float(x)) => Ok(Some(*x)),
        Some(Value::Int(i)) if ((*i as f64) as i128) == (*i as i128) => Ok(Some(*i as f64)),
        _ => Err(bad(k)),
    }
}

/// Python's ropts passes a key through when it is present, even as null.
fn num_present(op: &Value, k: &str) -> Result<Option<f64>, SmlError> {
    match op.get(k) {
        Some(Value::Null) => Err(bad(k)),
        _ => num(op, k),
    }
}

fn strict_str<'a>(op: &'a Value, k: &str) -> Result<Option<&'a str>, SmlError> {
    match op.get(k) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Str(x)) => Ok(Some(x)),
        _ => Err(bad(k)),
    }
}

/// Python's recall uses `query or key`: a falsy query falls back to the key, a truthy non-string fails.
fn recall_query(op: &Value) -> Result<Option<&str>, SmlError> {
    match op.get("query") {
        Some(Value::Str(q)) => Ok(Some(q)),
        None | Some(Value::Null) | Some(Value::Bool(false)) => Ok(None),
        Some(Value::Int(0)) => Ok(None),
        Some(Value::Float(x)) if *x == 0.0 => Ok(None),
        Some(Value::Arr(a)) if a.is_empty() => Ok(None),
        Some(Value::Obj(m)) if m.is_empty() => Ok(None),
        _ => Err(SmlError::Value("empty text".into())),
    }
}

fn s<'a>(op: &'a Value, k: &str) -> Option<&'a str> {
    op.get(k).and_then(Value::as_str)
}

fn i(op: &Value, k: &str) -> Result<i64, SmlError> {
    match op.get(k) {
        None => Ok(0),
        Some(Value::Int(x)) => Ok(*x),
        _ => Err(bad(k)),
    }
}

fn floats(op: &Value, k: &str) -> Result<Option<Vec<f64>>, SmlError> {
    match op.get(k) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Arr(a)) => Ok(Some(a.iter().map(|x| match x {
            Value::Float(f) => *f,
            Value::Int(i) if ((*i as f64) as i128) == (*i as i128) => *i as f64,
            _ => f64::NAN, // the store's number() check then refuses it, as Python's does
        }).collect())),
        _ => Err(bad(k)),
    }
}

fn hits(h: &[Hit]) -> Value {
    Value::Arr(h.iter().map(|x| Value::Arr(vec![x.record.get("id").cloned().unwrap_or(Value::Null),
                                                Value::Str(py_float_repr(x.score))])).collect())
}

fn ropts(op: &Value) -> Result<RetrieveOptions, SmlError> {
    let mut o = RetrieveOptions::default();
    match op.get("method") {
        None => {}
        Some(Value::Str(m)) => o.method = m.to_string(),
        _ => return Err(bad("method")),
    }
    match op.get("top_k") {
        None => {}
        Some(Value::Int(k)) => o.top_k = *k,
        _ => return Err(bad("top_k")),
    }
    if let Some(t) = num_present(op, "threshold")? { o.threshold = t; }
    if let Some(h) = num_present(op, "half_life")? { o.half_life = h; }
    o.key = match op.get("rkey") {
        None | Some(Value::Null) => None,
        Some(Value::Str(k)) => Some(k.clone()),
        Some(_) => Some("\u{0}".into()), // Python: a non-string key matches no stored key
    };
    o.embedding = floats(op, "qembedding")?;
    Ok(o)
}

fn popts(op: &Value) -> Result<PutOptions, SmlError> {
    Ok(PutOptions {
        timestamp: num(op, "timestamp")?,
        text: strict_str(op, "text")?.map(String::from),
        weight: num(op, "weight")?,
        protected: matches!(op.get("protected"), Some(Value::Bool(true))),
        supersedes: match op.get("supersedes") {
            None | Some(Value::Null) => None,
            Some(Value::Int(x)) => Some(*x),
            _ => return Err(SmlError::Value("unknown correction target".into())),
        },
        embedding: floats(op, "embedding")?,
        thermal_state: match op.get("thermal_state") {
            None | Some(Value::Null) => None,
            Some(Value::Str(t)) => Some(t.clone()),
            _ => return Err(SmlError::Value("unknown resource state".into())),
        },
    })
}

fn run(op: &Value) -> Result<Value, SmlError> {
    let dir = s(op, "dir").unwrap_or("").to_string();
    // Python calls the clock and refuses a non-number in number(); NaN reproduces that here.
    let t = match op.get("clock") {
        None => 1000.0,
        Some(Value::Float(x)) => *x,
        Some(Value::Int(i)) if ((*i as f64) as i128) == (*i as i128) => *i as f64,
        _ => f64::NAN,
    };
    let clock = Box::new(move || t);
    let name = s(op, "op").unwrap_or("");
    if name == "create" {
        MemoryStore::create(&dir, i(op, "max_records")?, i(op, "max_bytes")?, clock, None)?;
        return Ok(Value::Null);
    }
    if name == "repr" {
        let bits = match op.get("bits") { Some(Value::Arr(a)) => a.clone(), _ => vec![] };
        return Ok(Value::Arr(bits.iter().map(|h| {
            let x = f64::from_bits(u64::from_str_radix(h.as_str().unwrap_or("0"), 16).unwrap_or(0));
            Value::Str(if x.is_finite() { py_float_repr(x) } else { "nonfinite".into() })
        }).collect()));
    }
    if name == "file" {
        return Ok(match std::fs::read(std::path::Path::new(&dir).join("memory.json")) {
            Ok(b) => Value::Str(sml::text::sha256_hex(&b)),
            Err(_) => Value::Null,
        });
    }
    let m = MemoryStore::open(&dir, clock, None)?;
    let prov = op.get("provenance").cloned().unwrap_or(Value::Null);
    Ok(match name {
        "put" => Value::Int(m.put(s(op, "key").unwrap_or(""), s(op, "value").unwrap_or(""), &prov, &popts(op)?)?),
        "correct" => Value::Int(m.correct(i(op, "id")?, s(op, "value").unwrap_or(""), &prov, &popts(op)?)?),
        "revoke" => { m.revoke(i(op, "id")?, s(op, "reason").unwrap_or(""), &prov)?; Value::Null }
        "compact" => Value::Arr(m.compact(i(op, "target")?)?.into_iter().map(Value::Int).collect()),
        "retrieve" => hits(&m.retrieve(s(op, "query").unwrap_or(""), &ropts(op)?)?),
        "recall" => match m.recall(s(op, "key").unwrap_or(""), recall_query(op)?, &ropts(op)?)? {
            Recall::Known { value, evidence_ids, retrieval } => obj(vec![
                ("status", Value::Str("KNOWN".into())), ("value", Value::Str(value)),
                ("evidence_ids", Value::Arr(evidence_ids.into_iter().map(Value::Int).collect())),
                ("hits", hits(&retrieval))]),
            Recall::Unknown { reason, evidence_ids } => obj(vec![
                ("status", Value::Str("UNKNOWN".into())), ("reason", Value::Str(reason.into())),
                ("evidence_ids", Value::Arr(evidence_ids.into_iter().map(Value::Int).collect()))]),
        },
        "status" => {
            let st = m.storage_status()?;
            obj(vec![("generation", Value::Int(st.generation)), ("records", Value::Int(st.records as i64)),
                     ("bytes", Value::Int(st.bytes as i64)), ("max_records", Value::Int(st.max_records)),
                     ("max_bytes", Value::Int(st.max_bytes)),
                     ("incomplete_storage_detected", Value::Bool(st.incomplete_storage_detected))])
        }
        "cleanup" => { m.cleanup_incomplete()?; Value::Null }
        _ => return Err(SmlError::Value(format!("unknown op {}", name))),
    })
}

fn main() {
    let stdin = std::io::stdin();
    let mut out = std::io::stdout().lock();
    for line in stdin.lock().lines() {
        let line = line.expect("stdin");
        if line.trim().is_empty() {
            continue;
        }
        // R3-04: a line that is not one plain JSON object (bad JSON, duplicate fields, a BOM) is
        // "BadOp" on both sides of the protocol.
        let parsed = if line.starts_with('\u{feff}') { Err(String::from("BOM")) } else { json::parse(line.as_bytes()) };
        let res = match parsed {
            Err(_) => obj(vec![("ok", Value::Bool(false)), ("error", Value::Str("BadOp".into()))]),
            Ok(op) => match run(&op) {
                Ok(v) => obj(vec![("ok", Value::Bool(true)), ("result", v)]),
                Err(e) => obj(vec![("ok", Value::Bool(false)), ("error", Value::Str(e.class().into()))]),
            },
        };
        out.write_all(&json::canonical(&res).unwrap()).unwrap();
        out.write_all(b"\n").unwrap();
        out.flush().unwrap();
    }
}
