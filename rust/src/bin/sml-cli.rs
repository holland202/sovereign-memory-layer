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

fn f(op: &Value, k: &str) -> Option<f64> {
    op.get(k).and_then(Value::as_number)
}

fn s<'a>(op: &'a Value, k: &str) -> Option<&'a str> {
    op.get(k).and_then(Value::as_str)
}

fn i(op: &Value, k: &str) -> i64 {
    match op.get(k) {
        Some(Value::Int(x)) => *x,
        _ => 0,
    }
}

fn floats(v: Option<&Value>) -> Option<Vec<f64>> {
    match v {
        Some(Value::Arr(a)) => Some(a.iter().map(|x| x.as_number().unwrap_or(f64::NAN)).collect()),
        _ => None,
    }
}

fn hits(h: &[Hit]) -> Value {
    Value::Arr(h.iter().map(|x| Value::Arr(vec![x.record.get("id").cloned().unwrap_or(Value::Null),
                                                Value::Str(py_float_repr(x.score))])).collect())
}

fn ropts(op: &Value) -> RetrieveOptions {
    let mut o = RetrieveOptions::default();
    if let Some(m) = s(op, "method") { o.method = m.to_string(); }
    if let Some(Value::Int(k)) = op.get("top_k") { o.top_k = *k; }
    if let Some(t) = f(op, "threshold") { o.threshold = t; }
    if let Some(h) = f(op, "half_life") { o.half_life = h; }
    o.key = s(op, "rkey").map(String::from);
    o.embedding = floats(op.get("qembedding"));
    o
}

fn popts(op: &Value) -> PutOptions {
    PutOptions {
        timestamp: f(op, "timestamp"),
        text: s(op, "text").map(String::from),
        weight: f(op, "weight"),
        protected: matches!(op.get("protected"), Some(Value::Bool(true))),
        supersedes: match op.get("supersedes") { Some(Value::Int(x)) => Some(*x), _ => None },
        embedding: floats(op.get("embedding")),
        thermal_state: s(op, "thermal_state").map(String::from),
    }
}

fn run(op: &Value) -> Result<Value, SmlError> {
    let dir = s(op, "dir").unwrap_or("").to_string();
    let t = f(op, "clock").unwrap_or(1000.0);
    let clock = Box::new(move || t);
    let name = s(op, "op").unwrap_or("");
    if name == "create" {
        MemoryStore::create(&dir, i(op, "max_records"), i(op, "max_bytes"), clock, None)?;
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
        "put" => Value::Int(m.put(s(op, "key").unwrap_or(""), s(op, "value").unwrap_or(""), &prov, &popts(op))?),
        "correct" => Value::Int(m.correct(i(op, "id"), s(op, "value").unwrap_or(""), &prov, &popts(op))?),
        "revoke" => { m.revoke(i(op, "id"), s(op, "reason").unwrap_or(""), &prov)?; Value::Null }
        "compact" => Value::Arr(m.compact(i(op, "target"))?.into_iter().map(Value::Int).collect()),
        "retrieve" => hits(&m.retrieve(s(op, "query").unwrap_or(""), &ropts(op))?),
        "recall" => match m.recall(s(op, "key").unwrap_or(""), s(op, "query"), &ropts(op))? {
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
        let res = match json::parse(line.as_bytes()) {
            Err(e) => obj(vec![("ok", Value::Bool(false)), ("error", Value::Str(format!("BadOp: {}", e)))]),
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
