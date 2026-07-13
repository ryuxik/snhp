/* pyround.mjs — Python's round() for JS.  THE #1 FIDELITY TRAP.
 *
 * Python's built-in `round(x, ndigits)` on a float is correctly-rounded
 * round-HALF-to-EVEN (banker's rounding) of the EXACT binary value of the
 * double, re-parsed to the nearest double (CPython does this via David Gay's
 * dtoa mode 3 + strtod).  JavaScript's `Math.round` is round-half-UP and only
 * rounds to an integer, and `Number.prototype.toFixed` is round-half-away and
 * historically buggy.  Neither matches Python, so the rung/price rounding in
 * core.engine (`round(listv, 2)`, `round(lo + i*step, 2)`, `round(x, 9)`) would
 * drift by a cent and the F1 fidelity test would fail.
 *
 * We reproduce CPython exactly with BigInt: decompose the double into an exact
 * integer * 2^exp, scale by 10^ndigits as an exact rational, round-half-to-even
 * to an integer, then re-parse the decimal string with Number() (ECMAScript
 * Number(string) is itself correctly-rounded decimal->double, i.e. strtod).
 *
 * Validated against CPython on the tie cases that expose half-up vs half-even:
 *   round(0.125, 2) -> 0.12   round(0.375, 2) -> 0.38   round(2.675, 2) -> 2.67
 *   round(0.625, 2) -> 0.62   round(1.005, 2) -> 1.00
 */

// exact decomposition of a POSITIVE finite double: x === mant * 2^exp, mant BigInt.
function frexpExact(x) {
  const dv = new DataView(new ArrayBuffer(8));
  dv.setFloat64(0, x, false);
  const hi = dv.getUint32(0, false);
  const lo = dv.getUint32(4, false);
  const e = (hi >>> 20) & 0x7ff;
  let mant = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo >>> 0);
  let exp;
  if (e === 0) {
    exp = -1074;                       // subnormal
  } else {
    mant |= 1n << 52n;                 // restore the implicit leading 1
    exp = e - 1075;                    // bias 1023, minus 52 fraction bits
  }
  return { mant, exp };
}

// nearest integer to num/den (den > 0, num >= 0), ties to EVEN.
function roundHalfEvenBig(num, den) {
  const q = num / den;
  const twice = (num % den) * 2n;
  if (twice < den) return q;
  if (twice > den) return q + 1n;
  return q % 2n === 0n ? q : q + 1n;   // exact tie -> round to even
}

// nearest double to N * 10^(-nd) (N >= 0 BigInt) via correctly-rounded strtod.
function scaleToDouble(N, nd) {
  if (nd === 0) return Number(N);
  let s = N.toString();
  while (s.length <= nd) s = "0" + s;
  const i = s.length - nd;
  return Number(s.slice(0, i) + "." + s.slice(i));
}

/** Python round(x, ndigits) for finite x and ndigits >= 0. */
export function pyround(x, ndigits = 0) {
  if (!Number.isFinite(x)) return x;
  if (x === 0) return x;
  const neg = x < 0;
  const { mant, exp } = frexpExact(Math.abs(x));
  const pow10 = 10n ** BigInt(ndigits);
  let N;
  if (exp >= 0) {
    N = mant * (2n ** BigInt(exp)) * pow10;                 // already an integer
  } else {
    N = roundHalfEvenBig(mant * pow10, 2n ** BigInt(-exp)); // rational round
  }
  const val = scaleToDouble(N, ndigits);
  return neg ? -val : val;
}

export default pyround;

// browser convenience (dual-export): also hang it off the global.
if (typeof globalThis !== "undefined") {
  globalThis.SNHP_pyround = pyround;
}
