//! Python string and float behaviour the store depends on, reproduced exactly.

use md5::Md5;
use sha2::{Digest, Sha256};
use unicode_general_category::{get_general_category, GeneralCategory};
use unicode_normalization::UnicodeNormalization;

pub const DIM: usize = 384;

/// Python `str.isspace()`: Unicode bidi classes WS/B/S plus category Zs.
pub fn py_isspace(c: char) -> bool {
    matches!(c as u32,
        0x09..=0x0D | 0x1C..=0x20 | 0x85 | 0xA0 | 0x1680 | 0x2000..=0x200A | 0x2028 | 0x2029 | 0x202F | 0x205F | 0x3000)
}

/// Python `s.strip()` emptiness test.
pub fn py_blank(s: &str) -> bool {
    s.chars().all(py_isspace)
}

/// Python `s.split()` (no argument).
pub fn py_split(s: &str) -> Vec<&str> {
    s.split(py_isspace).filter(|w| !w.is_empty()).collect()
}

pub fn nfc(s: &str) -> String {
    s.nfc().collect()
}

/// Unicode categories Cc and Cf (Cs cannot occur in a Rust string).
pub fn has_control_or_format(s: &str) -> bool {
    s.chars().any(|c| matches!(get_general_category(c), GeneralCategory::Control | GeneralCategory::Format))
}

/// CPython >= 3.12 `sum()` over floats: Neumaier compensated summation, starting from int 0.
pub fn py_sum<I: IntoIterator<Item = f64>>(it: I) -> f64 {
    let mut f = 0.0f64;
    let mut c = 0.0f64;
    for x in it {
        let t = f + x;
        if f.abs() >= x.abs() {
            c += (f - t) + x;
        } else {
            c += (x - t) + f;
        }
        f = t;
    }
    if c != 0.0 && c.is_finite() {
        f += c;
    }
    f
}

fn mod_big_endian(bytes: &[u8], m: u32) -> usize {
    let mut acc: u32 = 0;
    for b in bytes {
        acc = (acc * 256 + *b as u32) % m;
    }
    acc as usize
}

/// The store's lexical hash embedding (NOT semantic), bit-identical to the Python reference.
pub fn hash_embedding_raw(text: &str) -> Vec<f64> {
    let mut out = vec![0.0f64; DIM];
    let lower = text.to_lowercase();
    // Streams the words (EXT-01): no vector of words is built.
    for (i, word) in lower.split(py_isspace).filter(|w| !w.is_empty()).enumerate() {
        let raw = word.as_bytes();
        let m = Md5::digest(raw);
        let s = Sha256::digest(raw);
        out[mod_big_endian(&m, DIM as u32)] += 1.0 / (i as f64 + 1.0);
        out[mod_big_endian(&s, DIM as u32)] += 0.5 / (i as f64 + 1.0);
    }
    out
}

pub fn sha256_hex(b: &[u8]) -> String {
    Sha256::digest(b).iter().map(|x| format!("{:02x}", x)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_matches_python_whitespace() {
        assert_eq!(py_split("a\x1cb  c\u{3000}d"), vec!["a", "b", "c", "d"]);
        assert!(py_blank(" \t\u{85}"));
    }

    #[test]
    fn neumaier_beats_naive() {
        let v = [1.0, 1e100, 1.0, -1e100];
        assert_eq!(py_sum(v), 2.0);
    }
}
