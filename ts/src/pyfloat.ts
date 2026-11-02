// CPython float behaviour the store depends on, reproduced exactly:
//   repr(float), sum() (Neumaier, CPython >= 3.12), and math.exp as glibc's x86_64 FMA build computes it.
// Exact arithmetic uses BigInt; no dependency.
import { EXP_TAB } from "./exp_table.ts";

const buf = new DataView(new ArrayBuffer(8));
export function bits(x: number): bigint {
  buf.setFloat64(0, x);
  return buf.getBigUint64(0);
}
export function fromBits(b: bigint): number {
  buf.setBigUint64(0, BigInt.asUintN(64, b));
  return buf.getFloat64(0);
}

/** x = m * 2^e exactly (m signed). Finite x only. */
function decompose(x: number): [bigint, number] {
  const b = bits(x);
  const neg = b >> 63n === 1n;
  const ex = Number((b >> 52n) & 0x7ffn);
  let m = b & 0xfffffffffffffn;
  let e: number;
  if (ex === 0) {
    e = -1074;
  } else {
    m |= 1n << 52n;
    e = ex - 1075;
  }
  return [neg ? -m : m, e];
}

/** Exactly 2^k as a double (k >= -1074); Infinity above 1023. */
function pow2(k: number): number {
  if (k > 1023) return Infinity;
  if (k >= -1022) return fromBits(BigInt(k + 1023) << 52n);
  return fromBits(1n << BigInt(k + 1074));
}

function bitLength(a: bigint): number {
  return a === 0n ? 0 : a.toString(2).length;
}

/** Round the exact value num * 2^e2 (num != 0) to the nearest double, ties to even. */
function roundExact(num: bigint, e2: number): number {
  const neg = num < 0n;
  const a = neg ? -num : num;
  const top = bitLength(a) - 1 + e2; // exponent of the leading bit
  const lsb = Math.max(top - 52, -1074);
  const drop = lsb - e2;
  let q: bigint;
  if (drop <= 0) {
    q = a << BigInt(-drop);
  } else {
    const d = BigInt(drop);
    q = a >> d;
    const rem = a & ((1n << d) - 1n);
    const half = 1n << (d - 1n);
    if (rem > half || (rem === half && (q & 1n) === 1n)) q += 1n;
  }
  // Number(q) <= 2^53 is exact; one multiplication by an exact power of two rounds nothing unless
  // the result overflows, which is then the correctly rounded infinity.
  const r = lsb > 971 ? Number(q) * pow2(lsb - 100) * pow2(100) : Number(q) * pow2(lsb);
  return neg ? -r : r;
}

/** Fused multiply-add a*b + c with a single rounding (IEEE 754 fusedMultiplyAdd). */
export function fma(a: number, b: number, c: number): number {
  if (!Number.isFinite(a) || !Number.isFinite(b) || !Number.isFinite(c)) return a * b + c;
  const [ma, ea] = decompose(a);
  const [mb, eb] = decompose(b);
  const [mc, ec] = decompose(c);
  const mp = ma * mb;
  const ep = ea + eb;
  let sum: bigint;
  let e: number;
  if (ep <= ec) {
    sum = mp + (mc << BigInt(ec - ep));
    e = ep;
  } else {
    sum = (mp << BigInt(ep - ec)) + mc;
    e = ec;
  }
  if (sum === 0n) {
    // Exact zero: -0 only when the product is a zero of negative sign and c is -0.
    const prodNeg = ((bits(a) ^ bits(b)) >> 63n) === 1n;
    return mp === 0n && prodNeg && Object.is(c, -0) ? -0 : 0;
  }
  return roundExact(sum, e);
}

/** CPython >= 3.12 sum() over floats: Neumaier compensated summation. */
export function pySum(xs: Iterable<number>): number {
  let f = 0.0;
  let c = 0.0;
  for (const x of xs) {
    const t = f + x;
    if (Math.abs(f) >= Math.abs(x)) c += (f - t) + x;
    else c += (x - t) + f;
    f = t;
  }
  if (c !== 0.0 && Number.isFinite(c)) f += c;
  return f;
}

// ---------------------------------------------------------------- math.exp (glibc 2.39, __ieee754_exp_fma)
// The constants and table come from ARM optimized-routines (MIT OR Apache-2.0 WITH LLVM-exception), as
// built into glibc. The operation order, including every fused multiply-add, follows the x86_64 FMA
// variant that CPython calls on a CPU with FMA. It was read from that variant's disassembly.
const INVLN2N = fromBits(0x40671547652b82fen); // 0x1.71547652b82fep+7
const SHIFT = fromBits(0x4338000000000000n); // 0x1.8p52
const NEGLN2HIN = fromBits(0xbf762e42fefa0000n); // -0x1.62e42fefa0000p-8
const NEGLN2LON = fromBits(0xbd0cf79abc9e3b3an); // -0x1.cf79abc9e3b3ap-47
const C2 = fromBits(0x3fdffffffffffdbdn); // 0x1.ffffffffffdbdp-2
const C3 = fromBits(0x3fc555555555543cn); // 0x1.555555555543cp-3
const C4 = fromBits(0x3fa55555cf172b91n); // 0x1.55555cf172b91p-5
const C5 = fromBits(0x3f81111167a4d017n); // 0x1.1111167a4d017p-7
const P1009 = pow2(1009);
const PM1022 = pow2(-1022);

export function exp(x: number): number {
  const xb = bits(x);
  let abstop = Number((xb >> 52n) & 0x7ffn);
  if (abstop - 0x3c9 >>> 0 > 0x3e) {
    if (abstop - 0x3c9 < 0) return 1.0 + x; // tiny |x|
    if (abstop > 0x408) {
      if (xb === 0xfff0000000000000n) return 0.0;
      if (abstop === 0x7ff) return 1.0 + x;
      return xb >> 63n ? 0.0 : Infinity;
    }
    abstop = 0; // large |x| below 1024: special case after the main computation
  }
  const kdShifted = fma(x, INVLN2N, SHIFT);
  const ki = bits(kdShifted);
  const kd = kdShifted - SHIFT;
  let r = fma(kd, NEGLN2HIN, x);
  r = fma(kd, NEGLN2LON, r);
  const p23 = fma(r, C3, C2);
  const idx = Number(ki & 0x7fn) * 2;
  const tail = fromBits(EXP_TAB[idx]);
  const top = BigInt.asUintN(64, ki << 45n);
  const sbits = BigInt.asUintN(64, EXP_TAB[idx + 1] + top);
  const tailR = r + tail;
  const r2 = r * r;
  const p45 = fma(r, C5, C4);
  const lo = fma(p23, r2, tailR);
  const tmp = fma(r2 * r2, p45, lo);
  if (abstop !== 0) {
    const scale = fromBits(sbits);
    return fma(scale, tmp, scale);
  }
  if ((ki & 0x80000000n) === 0n) {
    const scale = fromBits(sbits + 0xc0f0000000000000n);
    return fma(scale, tmp, scale) * P1009;
  }
  const scale = fromBits(sbits + 0x3fe0000000000000n);
  const st = tmp * scale;
  let y = scale + st;
  if (1.0 > y) {
    const hi = y + 1.0;
    const lo2 = (scale - y) + st;
    y = ((((1.0 - hi) + y) + lo2) + hi) - 1.0;
    if (y === 0) y = 0.0;
  }
  return y * PM1022;
}

// ---------------------------------------------------------------- repr(float)
const POW5: bigint[] = [1n];
function pow5(n: number): bigint {
  while (POW5.length <= n) POW5.push(POW5[POW5.length - 1] * 5n);
  return POW5[n];
}

const REPR_CACHE = new Map<number, string>();

/** CPython repr(float) (shortest round-trip, ties half to even, Python's exponent rules). Memoized:
 * the store re-encodes the same embeddings many times per operation. */
export function pyFloatRepr(x: number): string {
  if (x === 0 || !Number.isFinite(x)) return reprExact(x);
  let r = REPR_CACHE.get(x);
  if (r === undefined) {
    r = reprExact(x);
    if (REPR_CACHE.size > 200_000) REPR_CACHE.clear();
    REPR_CACHE.set(x, r);
  }
  return r;
}

function reprExact(x: number): string {
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  if (!Number.isFinite(x)) return Number.isNaN(x) ? "nan" : x > 0 ? "inf" : "-inf";
  // Digit count n of the shortest round-trip representation.
  const short = Math.abs(x).toExponential();
  const n = short.split("e")[0].replace(".", "").length;
  // Exact decimal expansion: |x| = digits * 10^exp10.
  const [m0, e] = decompose(x);
  const m = m0 < 0n ? -m0 : m0;
  let all: string;
  let exp10: number;
  if (e >= 0) {
    all = (m << BigInt(e)).toString();
    exp10 = 0;
  } else {
    all = (m * pow5(-e)).toString();
    exp10 = e;
  }
  // Leading-digit exponent of the exact value.
  let lead = all.length - 1 + exp10;
  const d = Array.from(all.slice(0, n), (c) => c.charCodeAt(0) - 48);
  while (d.length < n) d.push(0);
  const rest = all.slice(n);
  let up = false;
  if (rest.length > 0) {
    const r0 = rest.charCodeAt(0) - 48;
    if (r0 > 5) up = true;
    else if (r0 === 5) up = /[1-9]/.test(rest.slice(1)) || d[n - 1] % 2 === 1;
  }
  if (up) {
    let k = n;
    for (;;) {
      if (k === 0) {
        d.unshift(1);
        d.pop();
        lead += 1;
        break;
      }
      k -= 1;
      if (d[k] === 9) d[k] = 0;
      else {
        d[k] += 1;
        break;
      }
    }
  }
  while (d.length > 1 && d[d.length - 1] === 0) d.pop();
  const digits = d.join("");
  const decpt = lead + 1;
  let out = x < 0 ? "-" : "";
  if (decpt <= -4 || decpt > 16) {
    out += digits[0];
    if (digits.length > 1) out += "." + digits.slice(1);
    const ex = decpt - 1;
    out += "e" + (ex < 0 ? "-" : "+") + String(Math.abs(ex)).padStart(2, "0");
  } else if (decpt <= 0) {
    out += "0." + "0".repeat(-decpt) + digits;
  } else if (digits.length <= decpt) {
    out += digits + "0".repeat(decpt - digits.length) + ".0";
  } else {
    out += digits.slice(0, decpt) + "." + digits.slice(decpt);
  }
  return out;
}
