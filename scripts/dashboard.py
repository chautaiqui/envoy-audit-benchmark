#!/usr/bin/env python3
"""Static, offline HTML + SVG benchmark dashboard; stdlib only."""
import csv, html, json, math, statistics, sys
from collections import defaultdict
from pathlib import Path

def readcsv(path):
    return list(csv.DictReader(path.open())) if path.exists() else []
def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None

def fmt(v,unit='',precision=2):
    x=num(v)
    return 'N/A' if x is None else f'{x:,.{precision}f}{unit}'

def make_plot(title, series, unit='', height=250, ylabel=''):
    # series = [{name,color,points: [(x,value),...]}]
    colors={'Direct':'#14b8a6','Envoy':'#6366f1','Host':'#f59e0b','Envoy CPU':'#8b5cf6','Backend CPU':'#10b981','Envoy memory':'#8b5cf6','Backend memory':'#10b981','p99 Direct':'#14b8a6','p99 Envoy':'#6366f1'}
    cleaned=[]
    for s in series:
        pairs=sorted([(num(x),num(y)) for x,y in s['points'] if num(x) is not None and num(y) is not None])
        if pairs:cleaned.append((s['name'],colors.get(s['name'],'#3b82f6'),pairs))
    if not cleaned:
        return f'<section class="panel"><h3>{html.escape(title)}</h3><p class="muted">Không có dữ liệu đo hợp lệ (N/A).</p></section>'
    xs=[x for _,_,pairs in cleaned for x,y in pairs]; ys=[y for _,_,pairs in cleaned for x,y in pairs]
    xlo,xhi=min(xs),max(xs);xhi=xhi if xhi>xlo else xlo+1
    ylo=min(0,min(ys));yhi=max(ys);yhi=yhi*1.12 if yhi>0 else 1
    W,H=830,height;left,right,top,bottom=72,24,16,48
    pw=W-left-right;ph=H-top-bottom
    def sx(x):return left+pw*(x-xlo)/(xhi-xlo)
    def sy(y):return top+ph-(y-ylo)/(yhi-ylo)*ph
    v=[f'<section class="panel"><h3>{html.escape(title)}</h3><svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">']
    for k in range(5):
        val=ylo+(yhi-ylo)*k/4;yp=sy(val)
        v.append(f'<line x1="{left}" y1="{yp:.1f}" x2="{W-right}" y2="{yp:.1f}" stroke="#334155" opacity="0.35"/>')
        v.append(f'<text x="{left-10}" y="{yp+4:.1f}" text-anchor="end" fill="#94a3b8" font-size="12">{val:,.1f}</text>')
    xlabels=sorted(set(xs))
    if len(xlabels)>8:xlabels=[xlo+(xhi-xlo)*k/5 for k in range(6)]
    for x in xlabels:
        v.append(f'<text x="{sx(x):.1f}" y="{H-17}" text-anchor="middle" fill="#94a3b8" font-size="12">{x:g}</text>')
    for name,color,pairs in cleaned:
        pts=' '.join(f'{sx(x):.1f},{sy(y):.1f}' for x,y in pairs)
        v.append(f'<polyline points="{pts}" stroke="{color}" stroke-width="3" fill="none"/>')
        for x,y in pairs:v.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4" fill="{color}"><title>{html.escape(name)} x={x:g} y={y:.3f}</title></circle>')
    v.append('</svg><div class="legend">'+''.join(f'<span><b style="background:{color}"></b>{html.escape(name)}</span>' for name,color,_ in cleaned)+'</div>')
    if ylabel:v.append(f'<p class="muted">{html.escape(ylabel)} {html.escape(unit)}</p>')
    v.append('</section>')
    return ''.join(v)

def median_series(rows, key):
    d=defaultdict(list)
    for r in rows:
        x=num(r.get('concurrency'));y=num(r.get(key))
        if x is not None and y is not None:d[x].append(y)
    return [(c,statistics.median(values)) for c,values in sorted(d.items())]

def prometheus_case_summary(path):
    if not path.exists():return {}
    p=json.loads(path.read_text())
    out={}
    for name,series in p.get('series',{}).items():
        values=[val for s in series for _,val in s['points'] if val is not None]
        if values:out[name]={'avg':statistics.mean(values),'peak':max(values),'count':len(values)}
    return out

def main(root):
    root=Path(root).resolve();rows=readcsv(root/'summary.csv')
    if not rows:raise SystemExit('summary.csv missing. Run scripts/report.py first')
    bypath={path:[r for r in rows if r.get('path')==path] for path in ['direct','envoy']}
    content=[]
    content.append(make_plot('Throughput theo concurrency — median RPS',[{'name':p.capitalize(),'points':median_series(rr,'rps')} for p,rr in bypath.items()],ylabel='RPS'))
    content.append(make_plot('p99 theo concurrency — median (ms)',[{'name':'p99 '+p.capitalize(),'points':median_series(rr,'p99_ms')} for p,rr in bypath.items()],ylabel='ms'))
    content.append(make_plot('Tỷ lệ lỗi theo concurrency — median (%)',[{'name':p.capitalize(),'points':median_series(rr,'failure_pct')} for p,rr in bypath.items()],ylabel='%'))
    content.append(make_plot('CPU Envoy và Backend — tổng trung bình theo Pod (millicores)',[
        {'name':'Envoy CPU','points':median_series(bypath['envoy'],'envoy_cpu_sum_avg_m')},
        {'name':'Backend CPU','points':median_series(bypath['envoy'],'backend_cpu_sum_avg_m')}],ylabel='millicores'))
    content.append(make_plot('RAM Envoy và Backend — tổng peak (MiB)',[
        {'name':'Envoy memory','points':median_series(bypath['envoy'],'envoy_mem_sum_peak_mib')},
        {'name':'Backend memory','points':median_series(bypath['envoy'],'backend_mem_sum_peak_mib')}],ylabel='MiB'))
    content.append(make_plot('Host CPU peak theo concurrency (%)',[{'name':p.capitalize(),'points':median_series(rr,'host_cpu_peak_pct')} for p,rr in bypath.items()],ylabel='%'))
    prs=[]
    for r in rows:
        q=prometheus_case_summary(root/'prometheus'/f"{r['id']}.json")
        prs.append({'case':r['id'],**{k: v for k,v in q.items()}})
    prom_metrics=['envoy_downstream_rps','envoy_active_connections','envoy_pod_cpu_cores','envoy_pod_memory_bytes','envoy_upstream_5xx_rps','envoy_pod_cpu_throttle_rps']
    prom_values=[]
    for row in prs:
        q=[html.escape(row['case'])]
        for m in prom_metrics:
            val=row.get(m)
            if val and m.endswith('_bytes'):q.append(fmt(val['peak']/1024**2,' MiB'))
            elif val:q.append(fmt(val['avg']))
            else:q.append('N/A')
        prom_values.append(q)
    def table(headers, data):
        return '<div class="tablewrap"><table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in data)+'</tbody></table></div>'
    metrics=['id','path','concurrency','rps','p50_ms','p95_ms','p99_ms','failure_pct','host_cpu_peak_pct','envoy_cpu_sum_avg_m','envoy_mem_sum_peak_mib','backend_cpu_sum_avg_m','backend_mem_sum_peak_mib','node_throttled_s_sum']
    measurement_rows=[]
    for row in sorted(rows,key=lambda x:(num(x.get('concurrency')) or 0,x.get('id',''))):
        measurement_rows.append([row.get(k,'N/A') if k in ['id','path','concurrency'] else fmt(row.get(k)) for k in metrics])
    target_file=root/'prometheus'/'targets.json'
    target_note='Prometheus target health chưa được thu thập.'
    if target_file.exists():
        ts=json.loads(target_file.read_text()); target_note=f'{len(ts)} active targets, {sum(t.get("health")=="up" for t in ts)} UP; các target DOWN cần kiểm tra trước khi kết luận metrics thiếu.'
    pairs=readcsv(root/'comparison.csv');ratio=median_series(pairs,'envoy_to_direct_rps_pct')
    peak_env=max((num(r.get('rps')) or 0 for r in bypath['envoy']),default=0)
    peak_direct=max((num(r.get('rps')) or 0 for r in bypath['direct']),default=0)
    nps=sum(bool(row.get('envoy_cpu_sum_avg_m') and row['envoy_cpu_sum_avg_m']!='') for row in bypath['envoy'])
    stats=f'<div class="stats"><article><span>Peak Envoy RPS</span><strong>{peak_env:,.0f}</strong></article><article><span>Peak Direct RPS</span><strong>{peak_direct:,.0f}</strong></article><article><span>Cases</span><strong>{len(rows)}</strong></article><article><span>Envoy resource samples</span><strong>{nps}/{len(bypath["envoy"])}</strong></article></div>'
    charts=''.join(content)
    htmlout=f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Envoy Gateway Benchmark</title><style>
    :root{{color-scheme:dark}}body{{font:14px system-ui,Arial;background:#0b1220;color:#e2e8f0;max-width:1540px;margin:auto;padding:32px}}h1{{font-size:27px}}h2{{margin-top:40px}}.muted{{color:#94a3b8}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}}article,.panel{{border:1px solid #273449;border-radius:12px;background:#111d30;padding:18px}}article span{{display:block;color:#94a3b8}}article strong{{font-size:28px}}.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,580px),1fr));gap:16px}}.panel svg{{width:100%;height:auto}}.legend{{display:flex;gap:15px;flex-wrap:wrap}}.legend span b{{display:inline-block;width:13px;height:10px;margin-right:6px;border-radius:2px}}.tablewrap{{overflow-x:auto;background:#111d30;border-radius:10px}}table{{border-collapse:collapse;min-width:1100px;width:100%}}td,th{{border-bottom:1px solid #273449;padding:10px;text-align:right;white-space:nowrap}}td:first-child,th:first-child{{text-align:left}}th{{background:#1d2c44}}.warning{{border-left:3px solid #f59e0b;padding:12px;background:#2a211b}}code{{color:#93c5fd}}a{{color:#93c5fd}}
    </style></head><body><h1>Envoy Gateway — Benchmark Dashboard</h1><p class="muted">Offline HTML report · nguồn dữ liệu: {html.escape(str(root))}</p>{stats}<p class="warning"><b>Giới hạn:</b> Đây là phép đo trên VM kind. Không suy rộng thành production capacity. p95/p99 hoặc CPU/RAM thiếu sẽ được hiển thị N/A, không nội suy. PromQL thiếu series có thể do Prometheus chưa scrape endpoint hoặc dữ liệu đã hết retention.</p><h2>Biểu đồ benchmark</h2><div class="charts">{charts}</div><h2>Chi tiết từng case</h2>{table(metrics,measurement_rows)}<h2>Prometheus — HTTP và tài nguyên</h2><p>{html.escape(target_note)}</p>{table(['Case',*prom_metrics],prom_values)}<p class="muted">CPU_cores: CPU Prometheus tính theo core; RAM: peak MiB; RPS/connections/cpu: average trong khoảng query. Các Prometheus counters rate có window 1 phút nên số liệu của ca ngắn có thể lẫn các ca gần nhau.</p><h2>Đối chiếu</h2><p>Nguồn: <code>summary.csv</code>, <code>comparison.csv</code>, <code>pod-resources.csv</code>, <code>resources.jsonl</code> và <code>prometheus/*.json</code>. Metrics từ Prometheus có thể được bổ sung cho các lượt đo lịch sử qua <code>prom_enrich.py</code> nếu retention còn đủ.</p></body></html>'''
    (root/'dashboard.html').write_text(htmlout)
    print('Dashboard:',root/'dashboard.html')

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python3 scripts/dashboard.py RESULT_DIR')
    main(sys.argv[1])
