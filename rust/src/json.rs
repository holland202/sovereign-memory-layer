//! A small JSON model that reproduces Python's `json` exactly where the store depends on it:
//! `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`
//! for the checksummed canonical form, and a strict `json.loads` (duplicate keys refused).
//! Integers and floats are kept apart, as Python keeps `int` and `float` apart.

use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Arr(Vec<Value>),
    Obj(BTreeMap<String, Value>),
}

impl Value {
    pub fn as_str(&self) -> Option<&str> {
        if let Value::Str(s) = self { Some(s) } else { None }
    }
    pub fn as_obj(&self) -> Option<&BTreeMap<String, Value>> {
        if let Value::Obj(m) = self { Some(m) } else { None }
    }
    /// Python `type(x) in (int, float)`: numbers only, never bool.
    pub fn as_number(&self) -> Option<f64> {
        match self {
            Value::Int(i) => Some(*i as f64),
            Value::Float(f) => Some(*f),
            _ => None,
        }
    }
    pub fn get(&self, k: &str) -> Option<&Value> {
        self.as_obj().and_then(|m| m.get(k))
    }
}

// ------------------------------------------------------------------ encoding

/// Python `repr(float)` (CPython 'r' format with Py_DTSF_ADD_DOT_0).
pub fn py_float_repr(x: f64) -> String {
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0".into() } else { "0.0".into() };
    }
    // Rust's `{:e}` gives the shortest round-trip digit COUNT, but on an exact tie it rounds half
    // up, while CPython (David Gay's dtoa) rounds half to even: 1059438285926254.25 is "...254.2"
    // in Python and "...254.3" in Rust (found by differential test D2). So take only the length
    // n from Rust, and round the exact decimal expansion to n digits, half to even.
    let short = format!("{:e}", x);
    let n = short.split_once('e').unwrap().0.trim_start_matches('-').chars().filter(|c| *c != '.').count();
    let exact = format!("{:.800e}", x); // every finite f64 has at most 767 significant digits: exact
    let (mant, exp) = exact.split_once('e').expect("exponent");
    let mut exp: i32 = exp.parse().expect("exponent value");
    let neg = mant.starts_with('-');
    let all: Vec<u8> = mant.trim_start_matches('-').bytes().filter(|c| *c != b'.').map(|c| c - b'0').collect();
    let mut d: Vec<u8> = all[..n].to_vec();
    let rest = &all[n..];
    let round_up = match rest.first() {
        Some(&r) if r > 5 => true,
        Some(&5) => rest[1..].iter().any(|&c| c != 0) || d[n - 1] % 2 == 1,
        _ => false,
    };
    if round_up {
        let mut k = n;
        loop {
            if k == 0 {
                d.insert(0, 1);
                d.pop();
                exp += 1;
                break;
            }
            k -= 1;
            if d[k] == 9 {
                d[k] = 0;
            } else {
                d[k] += 1;
                break;
            }
        }
    }
    while d.len() > 1 && *d.last().unwrap() == 0 {
        d.pop();
    }
    let digits: String = d.iter().map(|c| (c + b'0') as char).collect();
    let decpt = exp + 1;
    let mut out = String::new();
    if neg {
        out.push('-');
    }
    if decpt <= -4 || decpt > 16 {
        out.push_str(&digits[..1]);
        if digits.len() > 1 {
            out.push('.');
            out.push_str(&digits[1..]);
        }
        let e = decpt - 1;
        out.push('e');
        out.push(if e < 0 { '-' } else { '+' });
        out.push_str(&format!("{:02}", e.abs()));
    } else if decpt <= 0 {
        out.push_str("0.");
        for _ in 0..(-decpt) {
            out.push('0');
        }
        out.push_str(&digits);
    } else {
        let d = decpt as usize;
        if digits.len() <= d {
            out.push_str(&digits);
            for _ in digits.len()..d {
                out.push('0');
            }
            out.push_str(".0");
        } else {
            out.push_str(&digits[..d]);
            out.push('.');
            out.push_str(&digits[d..]);
        }
    }
    out
}

fn encode_str(s: &str, out: &mut String) {
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

fn encode(v: &Value, out: &mut String) -> Result<(), String> {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Int(i) => out.push_str(&i.to_string()),
        Value::Float(f) => {
            if !f.is_finite() {
                return Err("Out of range float values are not JSON compliant".into());
            }
            out.push_str(&py_float_repr(*f));
        }
        Value::Str(s) => encode_str(s, out),
        Value::Arr(a) => {
            out.push('[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                encode(x, out)?;
            }
            out.push(']');
        }
        Value::Obj(m) => {
            // BTreeMap orders keys by UTF-8 bytes, which equals Python's code-point order.
            out.push('{');
            for (i, (k, x)) in m.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                encode_str(k, out);
                out.push(':');
                encode(x, out)?;
            }
            out.push('}');
        }
    }
    Ok(())
}

pub fn canonical(v: &Value) -> Result<Vec<u8>, String> {
    let mut s = String::new();
    encode(v, &mut s)?;
    Ok(s.into_bytes())
}

// ------------------------------------------------------------------ decoding

const MAX_DEPTH: usize = 512;

struct Parser<'a> {
    b: &'a [u8],
    i: usize,
}

impl<'a> Parser<'a> {
    fn ws(&mut self) {
        while self.i < self.b.len() && matches!(self.b[self.i], b' ' | b'\t' | b'\n' | b'\r') {
            self.i += 1;
        }
    }
    fn err<T>(&self, m: &str) -> Result<T, String> {
        Err(format!("{} at byte {}", m, self.i))
    }
    fn value(&mut self, depth: usize) -> Result<Value, String> {
        if depth > MAX_DEPTH {
            return self.err("maximum nesting depth exceeded");
        }
        self.ws();
        match self.b.get(self.i) {
            None => self.err("unexpected end"),
            Some(b'{') => {
                self.i += 1;
                let mut m = BTreeMap::new();
                self.ws();
                if self.b.get(self.i) == Some(&b'}') {
                    self.i += 1;
                    return Ok(Value::Obj(m));
                }
                loop {
                    self.ws();
                    if self.b.get(self.i) != Some(&b'"') {
                        return self.err("expected string key");
                    }
                    let k = self.string()?;
                    self.ws();
                    if self.b.get(self.i) != Some(&b':') {
                        return self.err("expected ':'");
                    }
                    self.i += 1;
                    let v = self.value(depth + 1)?;
                    if m.insert(k, v).is_some() {
                        return self.err("duplicate JSON key");
                    }
                    self.ws();
                    match self.b.get(self.i) {
                        Some(b',') => self.i += 1,
                        Some(b'}') => {
                            self.i += 1;
                            return Ok(Value::Obj(m));
                        }
                        _ => return self.err("expected ',' or '}'"),
                    }
                }
            }
            Some(b'[') => {
                self.i += 1;
                let mut a = Vec::new();
                self.ws();
                if self.b.get(self.i) == Some(&b']') {
                    self.i += 1;
                    return Ok(Value::Arr(a));
                }
                loop {
                    a.push(self.value(depth + 1)?);
                    self.ws();
                    match self.b.get(self.i) {
                        Some(b',') => self.i += 1,
                        Some(b']') => {
                            self.i += 1;
                            return Ok(Value::Arr(a));
                        }
                        _ => return self.err("expected ',' or ']'"),
                    }
                }
            }
            Some(b'"') => Ok(Value::Str(self.string()?)),
            Some(b't') if self.b[self.i..].starts_with(b"true") => {
                self.i += 4;
                Ok(Value::Bool(true))
            }
            Some(b'f') if self.b[self.i..].starts_with(b"false") => {
                self.i += 5;
                Ok(Value::Bool(false))
            }
            Some(b'n') if self.b[self.i..].starts_with(b"null") => {
                self.i += 4;
                Ok(Value::Null)
            }
            // Python accepts NaN/Infinity here; the store then refuses them (allow_nan=False in the
            // checksum). Refusing them at parse time gives the same outcome: IntegrityError.
            Some(c) if *c == b'-' || c.is_ascii_digit() => self.number(),
            _ => self.err("unexpected character"),
        }
    }
    fn number(&mut self) -> Result<Value, String> {
        let start = self.i;
        if self.b.get(self.i) == Some(&b'-') {
            self.i += 1;
        }
        match self.b.get(self.i) {
            Some(b'0') => self.i += 1,
            Some(c) if c.is_ascii_digit() => {
                while self.b.get(self.i).map_or(false, |c| c.is_ascii_digit()) {
                    self.i += 1;
                }
            }
            _ => return self.err("invalid number"),
        }
        let mut float = false;
        if self.b.get(self.i) == Some(&b'.') && self.b.get(self.i + 1).map_or(false, |c| c.is_ascii_digit()) {
            float = true;
            self.i += 1;
            while self.b.get(self.i).map_or(false, |c| c.is_ascii_digit()) {
                self.i += 1;
            }
        }
        if matches!(self.b.get(self.i), Some(b'e') | Some(b'E')) {
            let save = self.i;
            self.i += 1;
            if matches!(self.b.get(self.i), Some(b'+') | Some(b'-')) {
                self.i += 1;
            }
            if self.b.get(self.i).map_or(false, |c| c.is_ascii_digit()) {
                float = true;
                while self.b.get(self.i).map_or(false, |c| c.is_ascii_digit()) {
                    self.i += 1;
                }
            } else {
                self.i = save;
            }
        }
        let text = std::str::from_utf8(&self.b[start..self.i]).map_err(|e| e.to_string())?;
        if float {
            text.parse::<f64>().map(Value::Float).map_err(|e| e.to_string())
        } else {
            // Python accepts integers up to 4300 digits; this port refuses anything outside i64.
            text.parse::<i64>().map(Value::Int).map_err(|_| format!("integer out of supported range: {}", text))
        }
    }
    fn hex4(&mut self) -> Result<u32, String> {
        let h = self.b.get(self.i..self.i + 4).ok_or("truncated \\u escape")?;
        let s = std::str::from_utf8(h).map_err(|e| e.to_string())?;
        let v = u32::from_str_radix(s, 16).map_err(|_| "invalid \\u escape".to_string())?;
        if !s.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err("invalid \\u escape".into());
        }
        self.i += 4;
        Ok(v)
    }
    fn string(&mut self) -> Result<String, String> {
        self.i += 1; // opening quote
        let mut out = String::new();
        loop {
            let start = self.i;
            while self.i < self.b.len() && self.b[self.i] != b'"' && self.b[self.i] != b'\\' && self.b[self.i] >= 0x20 {
                self.i += 1;
            }
            out.push_str(std::str::from_utf8(&self.b[start..self.i]).map_err(|e| e.to_string())?);
            match self.b.get(self.i) {
                None => return self.err("unterminated string"),
                Some(b'"') => {
                    self.i += 1;
                    return Ok(out);
                }
                Some(b'\\') => {
                    self.i += 1;
                    let c = *self.b.get(self.i).ok_or("truncated escape")?;
                    self.i += 1;
                    match c {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{08}'),
                        b'f' => out.push('\u{0c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let u = self.hex4()?;
                            if (0xD800..0xDC00).contains(&u) {
                                if self.b.get(self.i..self.i + 2) == Some(b"\\u") {
                                    self.i += 2;
                                    let l = self.hex4()?;
                                    if !(0xDC00..0xE000).contains(&l) {
                                        return Err("lone surrogate in string".into());
                                    }
                                    let cp = 0x10000 + ((u - 0xD800) << 10) + (l - 0xDC00);
                                    out.push(char::from_u32(cp).ok_or("invalid code point")?);
                                } else {
                                    // Python keeps a lone surrogate, then fails to encode it: IntegrityError.
                                    return Err("lone surrogate in string".into());
                                }
                            } else if (0xDC00..0xE000).contains(&u) {
                                return Err("lone surrogate in string".into());
                            } else {
                                out.push(char::from_u32(u).ok_or("invalid code point")?);
                            }
                        }
                        _ => return self.err("invalid escape"),
                    }
                }
                Some(_) => return self.err("invalid control character in string"),
            }
        }
    }
}

/// Strict `json.loads(bytes)`: UTF-8 (a leading UTF-8 BOM is skipped, as Python does), duplicate
/// keys refused, nothing but whitespace after the value.
pub fn parse(bytes: &[u8]) -> Result<Value, String> {
    let b = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF][..]).unwrap_or(bytes);
    std::str::from_utf8(b).map_err(|e| format!("invalid UTF-8: {}", e))?;
    let mut p = Parser { b, i: 0 };
    let v = p.value(0)?;
    p.ws();
    if p.i != b.len() {
        return p.err("extra data");
    }
    Ok(v)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn float_repr_matches_python_examples() {
        for (x, s) in [(1e-5, "1e-05"), (1e16, "1e+16"), (1e15, "1000000000000000.0"), (0.0001, "0.0001"),
                       (1000.0, "1000.0"), (0.1, "0.1"), (-2.5, "-2.5"), (1.5e16, "1.5e+16"), (123.456, "123.456"),
                       (5e-324, "5e-324"), (1.7976931348623157e308, "1.7976931348623157e+308"), (-0.0, "-0.0"),
                       (f64::from_bits(0x430e1c6d958d7b72), "1059438285926254.2")] {
            assert_eq!(py_float_repr(x), s, "{}", x);
        }
    }

    #[test]
    fn duplicate_keys_and_trailing_data_refused() {
        assert!(parse(b"{\"a\":1,\"a\":2}").is_err());
        assert!(parse(b"{} x").is_err());
        assert!(parse(b"[1,]").is_err());
        assert!(parse(b"NaN").is_err());
        assert!(parse(b"01").is_err());
    }

    #[test]
    fn roundtrip_int_float_distinction() {
        let v = parse(b"[1,1.0,1e2,-0,\"\\u00e9\\n\"]").unwrap();
        assert_eq!(String::from_utf8(canonical(&v).unwrap()).unwrap(), "[1,1.0,100.0,0,\"\u{e9}\\n\"]");
    }
}
