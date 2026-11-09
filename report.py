#!/usr/bin/env python3
"""Summarize hey benchmark files created by envoy-audit-benchmark/scripts/benchmark.sh.
Usage: python3 report_benchmark.py /root/envoy-audit-benchmark/bench-results-YYYYmmdd-HHMMSS
No third-party Python packages required.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

FIELDS = ['scenario','concurrency','duration_s','requests','rps','avg_ms','p50_ms','p90_ms','p95_ms','p99_ms','fastest_ms','slowest_ms','http_200','http_non200','transport_errors','success_pct']

def num(pat, s):
    m = re.search(pat, s, re.I | re.M)
    return float(m.group(1)) if m else None

def parse(path):
    m = re.fullmatch(r'(direct|envoy)(-warmup)?-c(\d+)\.txt', path.name)
    if not m:
        return None
    name, warmup, concurrency = m.groups()
    s = path.read_text(errors='replace')
    def ms(p):
        v = num(p, s)
        return round(v*1000, 4) if v is not None else None
    # Hey versions often use e.g. '50% in 0.0012 secs' and 'Requests/sec: 1234.56'.
    stats = {
        'scenario': name + ('-warmup' if warmup else ''),
        'concurrency': int(concurrency),
        'duration_s': num(r'^\s*Total:\s*([\d.]+)\s*secs', s),
        'requests': None,
        'rps': num(r'^\s*Requests/sec:\s*([\d.]+)', s),
        'avg_ms': ms(r'^\s*Average:\s*([\d.]+)\s*secs'),
        'fastest_ms': ms(r'^\s*Fastest:\s*([\d.]+)\s*secs'),
        'slowest_ms': ms(r'^\s*Slowest:\s*([\d.]+)\s*secs'),
        'p50_ms': ms(r'^\s*50%\s+in\s+([\d.]+)\s*secs'),
        'p90_ms': ms(r'^\s*90%\s+in\s+([\d.]+)\s*secs'),
        'p95_ms': ms(r'^\s*95%\s+in\s+([\d.]+)\s*secs'),
        'p99_ms': ms(r'^\s*99%\s+in\s+([\d.]+)\s*secs'),
        'http_200': 0,
        'http_non200': 0,
        'transport_errors': 0,
        'success_pct': None,
    }
    # The 'Status code distribution:' section contains '[200] 100 responses'.
    status_section = re.search(r'^\s*Status code distribution:\s*\n(.*?)(?=\n\s*(?:Error distribution:|$))',s,re.M|re.S|re.I)
    # Regex above may miss if a different section follows; parse line by line instead.
    in_status = False
    for line in s.splitlines():
        if line.strip().startswith('Status code distribution:'):
            in_status = True
            continue
        if in_status:
            code_match = re.match(r'^\s*\[(\d{3})\]\s+(\d+)\s+responses?',line)
            if code_match:
                code, count = int(code_match.group(1)),int(code_match.group(2))
                if code == 200: stats['http_200'] += count
                else: stats['http_non200'] += count
            elif line.strip() and not re.match(r'^\s*\[', line):
                in_status = False
    error_section = re.search(r'^\s*Error distribution:\s*\n(.*?)(?=\n\s*\S[^\n]*:\s*\n|\Z)',s,re.M|re.S|re.I)
    if error_section:
        for line in error_section.group(1).splitlines():
            err = re.match(r'^\s*\[(\d+)\]\s+\S',line)
            if err: stats['transport_errors'] += int(err.group(1))
    stats['requests'] = stats['http_200'] + stats['http_non200']
    if stats['requests']:
        stats['success_pct'] = round(100*stats['http_200']/stats['requests'], 3)
    return stats

def cell(v, digits=2):
    if v is None: return 'N/A'
    if isinstance(v, float): return f'{v:.{digits}f}'
    return str(v)

def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 report_benchmark.py /path/to/bench-results-YYYYmmdd-HHMMSS')
    root = Path(sys.argv[1]).expanduser()
    if not root.is_dir(): raise SystemExit(f'Not a directory: {root}')
    rows = sorted(filter(None, (parse(p) for p in root.glob('*.txt'))), key=lambda x: (x['concurrency'],x['scenario']))
    if not rows: raise SystemExit('No hey output files found (direct-c*.txt / envoy-c*.txt)')
    with (root/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(rows)
    measurements=[r for r in rows if not r['scenario'].endswith('-warmup')]
    by_c=defaultdict(dict)
    for r in measurements: by_c[r['concurrency']][r['scenario']]=r
    lines=[
        '# Envoy Gateway Benchmark Report',
        '',
        f'Source: `{root.name}` · Generated from actual hey output (no fabricated measurements).',
        '',
        '## Results',
        '',
        '| Concurrency | Path | RPS | p50 (ms) | p95 (ms) | p99 (ms) | HTTP 200 | Non-200 | Transport errors |',
        '|---:|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in measurements:
        lines.append('| '+ ' | '.join([cell(r['concurrency']),r['scenario'],cell(r['rps']),cell(r['p50_ms']),cell(r['p95_ms']),cell(r['p99_ms']),cell(r['http_200']),cell(r['http_non200']),cell(r['transport_errors'])])+' |')
    lines += ['', '## Direct vs Envoy', '', '| Concurrency | Envoy / Direct RPS | p99 delta (ms) | Notes |', '|---:|---:|---:|---|']
    for c, pair in sorted(by_c.items()):
        d,e=pair.get('direct'),pair.get('envoy')
        if not d or not e:
            lines.append(f'| {c} | N/A | N/A | Missing direct or envoy measurement |')
            continue
        ratio=100*e['rps']/d['rps'] if e['rps'] and d['rps'] else None
        delta=e['p99_ms']-d['p99_ms'] if e['p99_ms'] is not None and d['p99_ms'] is not None else None
        notes=[]
        if e['http_non200'] or d['http_non200']: notes.append('Non-200 responses detected')
        if e['transport_errors'] or d['transport_errors']: notes.append('Transport errors detected')
        if not notes: notes.append('Review load-generator saturation and resource metrics')
        lines.append(f"| {c} | {cell(ratio)}% | {cell(delta)} | {'; '.join(notes)} |")
    lines += [
        '', '## Interpretation and limitations',
        '',
        '- `RPS ratio` = Envoy RPS / Direct RPS × 100%; it is not a pure measurement of Envoy CPU overhead.',
        '- `p99 delta` = Envoy p99 − Direct p99 at the same concurrency. Compare only when response size, error rate and backend conditions match.',
        '- HTTP error counts and transport errors are different. Read the original hey logs if counts are suspicious.',
        '- This script does not collect CPU, RAM, throttling, Prometheus metrics, or configuration state. Collect those independently.',
        '- Both paths use Kubernetes NodePort; on a single-host kind lab the client shares host resources with proxy and backends.',
        '- For capacity conclusions, fix Envoy placement, run at least 3 repetitions per case, ideally use an external load generator and report medians.',
        '', '## Raw files', '',
    ]
    lines += [f'- `{p.name}`' for p in sorted(root.glob('*.txt'))]
    (root/'report.md').write_text('\n'.join(lines)+'\n')
    print(f'Parsed {len(rows)} files. Generated:\n  {root}/summary.csv\n  {root}/report.md')
    print('\n'.join(lines[7: min(7+len(measurements)+2, 22)]))

if __name__=='__main__': main()

