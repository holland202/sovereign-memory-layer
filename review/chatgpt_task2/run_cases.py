"""AI-generated (ChatGPT): bounded, synthetic Python/Rust parity probes.

Exit 1 means an observed parity failure, not an expected-success xfail.
No source under test is edited. Full inputs, outputs and diffs are retained.
"""
import argparse
import difflib
import hashlib
import json
import math
from pathlib import Path
import platform
import shlex
import struct
import subprocess
import sys
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sml.memory import MemoryStore, canonical, digest

PROV = {'source': 'synthetic-chatgpt-review', 'locator': 'case-1',
        'sha256': hashlib.sha256(b'synthetic review data').hexdigest()}
E = [1.0] + [0.0] * 383


def put(**kw):
    return dict(op='put', key='k', value='v', provenance=PROV, **kw)


def create(**kw):
    return dict(op='create', max_records=kw.get('max_records', 20),
                max_bytes=kw.get('max_bytes', 200000))


def cases():
    c = {}
    def add(name, ops, fixture=None):
        c[name] = (ops, fixture)

    for name, upper, lower in [('cyrillic_tje', '\u1c89', '\u1c8a'),
                               ('garay', '\U00010d50', '\U00010d70'),
                               ('ascii_control', 'ABC', 'abc'),
                               ('greek_control', 'ΟΣ', 'ος')]:
        add('unicode_' + name, [create(), put(text=upper), {'op': 'file'},
                               {'op': 'recall', 'key': 'k', 'query': lower},
                               {'op': 'recall', 'key': 'k', 'query': upper}])
    ws = ''.join(chr(n) for n in range(0x110000) if chr(n).isspace())
    add('whitespace_all_python', [create(), put(text='a' + ws + 'b'), {'op': 'file'},
                                 {'op': 'retrieve', 'query': 'a b'}])
    add('nfc_control', [create(), dict(put(), key='cafe\u0301'), {'op': 'file'},
                        {'op': 'recall', 'key': 'café', 'query': 'v'}])
    for field, value in [('weight', True), ('timestamp', 'invalid'), ('embedding', 'invalid'),
                         ('thermal_state', 3), ('supersedes', True)]:
        add('option_' + field, [create(), put(**{field: value}), {'op': 'file'}, {'op': 'status'}])
    for field, value in [('top_k', 1.0), ('threshold', True), ('qembedding', 'invalid')]:
        add('retrieve_' + field, [create(), put(text='match'),
                                {'op': 'retrieve', 'query': 'match', field: value}, {'op': 'file'}])
    add('timestamp_integer_rounding', [create(), put(clock=2**53, timestamp=2**53+1, embedding=E),
                                      {'op': 'file'}, {'op': 'status'}])
    for name, clock, timestamp in [('zero', 0.0, 0.0), ('negative_zero', -0.0, -0.0),
                                    ('subnormal', 5e-324, 5e-324),
                                    ('future_float', 1.0, math.nextafter(1.0, math.inf)),
                                    ('maximum', sys.float_info.max, sys.float_info.max)]:
        add('timestamp_' + name, [create(), put(clock=clock, timestamp=timestamp, embedding=E),
                                  {'op': 'file'}, {'op': 'retrieve', 'query': 'q', 'qembedding': E,
                                                  'clock': clock, 'method': 'recency'}])
    add('snapshot_future_integer', [{'op': 'status'},
         {'op': 'recall', 'key': 'k', 'query': 'q', 'qembedding': E, 'clock': 2**53}, {'op': 'file'}],
        'future_integer')
    add('snapshot_duplicate_key', [{'op': 'status'}, {'op': 'file'}], 'duplicate')
    add('snapshot_utf8_bom', [{'op': 'status'}, {'op': 'file'}], 'bom')
    add('snapshot_lone_surrogate', [{'op': 'status'}, {'op': 'file'}], 'surrogate')
    add('json_duplicate_command', [create(), '{"op":"put","dir":"@DIR@","key":"k",'
        '"value":"first","value":"second","provenance":' + json.dumps(PROV) + '}',
        {'op': 'status'}, {'op': 'file'}])
    add('json_bom_command', ['\ufeff' + json.dumps(create()), {'op': 'file'}])
    for label, size, cap in [('accepted', 65536, 200000), ('refused', 65536, 4096)]:
        add('large_value_' + label, [create(max_bytes=cap), dict(put(embedding=E), value='x'*size),
                                    {'op': 'file'}, {'op': 'status'}])
    add('compact_chain_ties', [create(), put(weight=0.5, embedding=E),
        dict(put(weight=0.5, embedding=E), key='other'),
        {'op': 'correct', 'id': 1, 'value': 'corrected', 'provenance': PROV, 'weight': 0.5, 'embedding': E},
        {'op': 'compact', 'target': 2}, {'op': 'file'}, {'op': 'status'},
        {'op': 'retrieve', 'query': 'q', 'qembedding': E}])
    add('compact_protected_ties', [create(), put(weight=0.5, embedding=E, protected=True),
        dict(put(weight=0.5, embedding=E), key='other'),
        {'op': 'compact', 'target': 1}, {'op': 'file'}, {'op': 'compact', 'target': 0}, {'op': 'file'}])
    vals = {0.0, 5e-324, sys.float_info.max, 1059438285926254.25}
    for exponent in range(-323, 309):
        v = float('1e' + str(exponent))
        vals.update([v, math.nextafter(v, 0.0), math.nextafter(v, math.inf)])
    bits = sorted({struct.pack('>d', sign*v).hex() for v in vals for sign in [-1, 1] if math.isfinite(v)})
    add('float_decimal_neighborhoods', [{'op': 'repr', 'bits': bits}])
    return c


def fixture(kind, work):
    d = work / 'fixture-source'
    m = MemoryStore(d, create=True, max_records=20, max_bytes=200000, clock=lambda: 1000.0)
    m.put('k', 'v', provenance=PROV, embedding=E)
    state = m.snapshot()
    if kind == 'future_integer':
        state['records'][0]['timestamp'] = 2**53 + 1
        state['records'][0]['recorded_at'] = 2**53 + 2
    raw = canonical({'payload': state, 'sha256': digest(state)}) + b'\n'
    if kind == 'duplicate':
        raw = raw.replace(b'"schema":1', b'"schema":1,"schema":1')
    elif kind == 'bom':
        raw = b'\xef\xbb\xbf' + raw
    elif kind == 'surrogate':
        raw = raw.replace(b'"value":"v"', b'"value":"\\ud800"')
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', action='append', default=[])
    ap.add_argument('--out', type=Path, default=Path(__file__).parent / 'raw')
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = cases()
    if a.case:
        selected = {k: selected[k] for k in a.case}
    summary = []
    for name, (ops, kind) in selected.items():
        dest = out / name
        dest.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='sml-probe-') as tmp:
            work = Path(tmp)
            raw = fixture(kind, work) if kind else None
            if raw is not None:
                (dest / 'fixture.memory.json').write_bytes(raw)
            results = {}
            commands = []
            for side, cmd in [('python', ['python3', 'tools/py_cli.py', '.']),
                              ('rust', ['rust/target/release/sml-cli'])]:
                d = work / side
                if raw is not None:
                    d.mkdir()
                    (d / 'memory.json').write_bytes(raw)
                lines = []
                for op in ops:
                    if isinstance(op, dict):
                        lines.append(json.dumps(dict(op, dir=str(d)), ensure_ascii=True))
                    elif op.startswith('\ufeff'):
                        lines.append('\ufeff' + json.dumps(dict(json.loads(op[1:]), dir=str(d))))
                    else:
                        lines.append(op.replace('@DIR@', str(d)))
                inputs = '\n'.join(lines) + '\n'
                infile = dest / (side + '.input.jsonl')
                infile.write_text(inputs)
                commands.append('cd ' + shlex.quote(str(ROOT)) + '\n' +
                                shlex.join(cmd) + ' < ' + shlex.quote(str(infile)))
                try:
                    p = subprocess.run(cmd, cwd=ROOT, input=inputs, text=True,
                                       capture_output=True, timeout=60)
                    result = dict(exit=p.returncode, stdout=p.stdout, stderr=p.stderr)
                except subprocess.TimeoutExpired as e:
                    result = dict(exit='TIMEOUT', stdout=(e.stdout or b'').decode(),
                                  stderr=(e.stderr or b'').decode())
                for stream in ['stdout', 'stderr']:
                    (dest / (side + '.' + stream + '.txt')).write_text(result[stream])
                results[side] = result
            delta = ''.join(difflib.unified_diff(results['python']['stdout'].splitlines(True),
                                                results['rust']['stdout'].splitlines(True),
                                                fromfile='python', tofile='rust'))
            (dest / 'diff.txt').write_text(delta)
            (dest / 'commands.txt').write_text('\n'.join(commands) + '\n')
            equal = (results['python'] == results['rust'] and
                     results['python']['exit'] == 0 and
                     len(results['python']['stdout'].splitlines()) == len(ops))
            summary.append(dict(case=name, equal=equal,
                                exits={k: v['exit'] for k, v in results.items()}, operations=len(ops)))
            print(name + ': ' + ('IDENTICAL' if equal else 'MISMATCH'), flush=True)
    source = ['sml/memory.py', 'rust/src/store.rs', 'rust/src/text.rs', 'rust/src/json.rs',
              'rust/src/bin/sml-cli.rs', 'tools/py_cli.py', 'tools/differential.py', 'rust/Cargo.lock']
    metadata = dict(python=sys.version, python_unicode=unicodedata.unidata_version,
                    platform=platform.platform(),
                    source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source},
                    binary_sha256=hashlib.sha256((ROOT / 'rust/target/release/sml-cli').read_bytes()).hexdigest(),
                    results=summary)
    (out / 'results.json').write_text(json.dumps(metadata, indent=2) + '\n')
    bad = sum(not r['equal'] for r in summary)
    print(f'TOTAL {len(summary)} sequences: {len(summary)-bad} identical, {bad} mismatches')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
