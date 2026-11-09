#!/usr/bin/env python3
"""Report hey and resource telemetry from run.py. Python stdlib only."""
import csv, json, re, statistics, sys
from collections import defaultdict
from pathlib import Path

FLOAT=r'([0-9]+(?:\.[0-9]+)?)'

def findnum(pattern,s):
    m=re.search(pattern,s,re.I|re.M)
    return float(m.group(1)) if m else None

def parse_hey(path):
    s=Path(path).read_text(errors='replace') if Path(path).exists() else ''
    result={'rps':findnum(r'^\s*Requests/sec:\s*'+FLOAT,s),
      'duration_s':findnum(r'^\s*Total:\s*'+FLOAT+r'\s*(?:secs|seconds|s)?',s),
      'avg_ms':None,'p50_ms':None,'p90_ms':None,'p95_ms':None,'p99_ms':None,
      'http_200':0,'http_non200':0,'transport_errors':0,'status':{}}
    for key,regex in [('avg_ms',r'^\s*Average:\s*'+FLOAT+r'\s*(?:secs|seconds|s)?'),('p50_ms',r'^\s*50(?:\.0)?%\s+in\s+'+FLOAT+r'\s*(?:secs|seconds|s)?'),('p90_ms',r'^\s*90(?:\.0)?%\s+in\s+'+FLOAT+r'\s*(?:secs|seconds|s)?'),('p95_ms',r'^\s*95(?:\.0)?%\s+in\s+'+FLOAT+r'\s*(?:secs|seconds|s)?'),('p99_ms',r'^\s*99(?:\.0)?%\s+in\s+'+FLOAT+r'\s*(?:secs|seconds|s)?')]:
        n=findnum(regex,s);result[key]=round(n*1000,4) if n is not None else None
    section=''
    for line in s.splitlines():
        v=line.strip()
        if v.startswith('Status code distribution:'):
            section='status';continue
        if v.startswith('Error distribution:'):
            section='error';continue
        if section=='status':
            m=re.match(r'^\[(\d{3})\]\s+(\d+)\s+responses?',v)
            if m:
                code,count=m.group(1),int(m.group(2));result['status'][code]=result['status'].get(code,0)+count
                if code=='200':result['http_200']+=count
                else:result['http_non200']+=count
            elif v and not v.startswith('['):section=''
        elif section=='error':
            m=re.match(r'^\[(\d+)\]\s+\S',v)
            if m:result['transport_errors']+=int(m.group(1))
            elif v and not v.startswith('['):section=''
    result['completed_responses']=result['http_200']+result['http_non200']
    result['total_outcomes']=result['completed_responses']+result['transport_errors']
    return result

def count_failure_pct(s):
    if not s['total_outcomes']:return None
    return round(100*(s['http_non200']+s['transport_errors'])/s['total_outcomes'],4)

def mb(value):
    m=re.match(r'^\s*([0-9.]+)\s*([kKmMgGtTpP]?i?[bB]?)',value)
    if not m:return None
    x=float(m.group(1));u=m.group(2).lower().replace('b','')
    powers={'':0,'k':1,'m':2,'g':3,'t':4,'p':5,'ki':1,'mi':2,'gi':3,'ti':4,'pi':5}
    return x*(1024 if 'i' in u else 1000)**powers.get(u,0)/1024**2

def quant(items,func=max):
    return round(func(items),3) if items else None

def stats_resources(case):
    pod_samples=defaultdict(lambda:{'cpu_m':[],'mem_mib':[]})
    dock_samples=defaultdict(lambda:{'cpu_pct':[],'mem_mib':[],'net_rx_mib':[],'net_tx_mib':[]})
    node_samples=defaultdict(lambda:{'cpu_m':[],'mem_mib':[]})
    host_cpu=[];host_load=[];host_mem_used=[];sample_count=0
    p=case/'resources.jsonl'
    if p.exists():
        for line in p.read_text(errors='replace').splitlines():
            try:x=json.loads(line)
            except ValueError:continue
            sample_count+=1
            h=x.get('host',{})
            if h.get('cpu_util_pct') is not None:host_cpu.append(h['cpu_util_pct'])
            if h.get('load1') is not None:host_load.append(h['load1'])
            if h.get('mem_total_kib') and h.get('mem_available_kib'):
                host_mem_used.append((h['mem_total_kib']-h['mem_available_kib'])/1024**2)
            for line2 in x.get('pods','').splitlines():
                a=line2.split()
                if len(a)<4:continue
                ns,name,cpu,mem=a[:4]
                if not(ns=='envoy-gateway-system' or ns=='platform-test'):continue
                try:
                    cm=float(cpu[:-1]) if cpu.endswith('m') else float(cpu)*1000
                    mm=mb(mem)
                except ValueError:continue
                item=pod_samples[f'{ns}/{name}'];item['cpu_m'].append(cm)
                if mm is not None:item['mem_mib'].append(mm)
            for line2 in x.get('nodes','').splitlines():
                a=line2.split()
                if len(a)<3:continue
                name,cpu=a[:2];mem=a[3] if len(a)>=4 else None
                if name.startswith('envoy-lab-'):
                    try:cm=float(cpu[:-1]) if cpu.endswith('m') else float(cpu)*1000
                    except ValueError:continue
                    node_samples[name]['cpu_m'].append(cm)
                    mm=mb(mem or '')
                    if mm is not None:node_samples[name]['mem_mib'].append(mm)
            for line2 in x.get('docker','').splitlines():
                a=line2.split('|')
                if len(a)<4:continue
                name,cpu,mem,net=a[:4]
                try:c=float(cpu.strip().rstrip('%'))
                except ValueError:continue
                item=dock_samples[name];item['cpu_pct'].append(c)
                memvalue=mb(mem.split('/')[0].strip());netbits=net.split('/')
                if memvalue is not None:item['mem_mib'].append(memvalue)
                if len(netbits)==2:
                    rx=mb(netbits[0].strip());tx=mb(netbits[1].strip())
                    if rx is not None:item['net_rx_mib'].append(rx)
                    if tx is not None:item['net_tx_mib'].append(tx)
    rj=json.loads((case/'run.json').read_text())
    throttling=[]
    for node,start in rj.get('cgroup_before',{}).items():
        end=rj.get('cgroup_after',{}).get(node,{})
        a=start.get('throttled_usec');b=end.get('throttled_usec')
        n0=start.get('nr_throttled');n1=end.get('nr_throttled')
        if a is not None and b is not None:
            throttling.append({'node':node,'throttled_s':max(0,b-a)/1e6,'nr_throttled':max(0,n1-n0) if n1 is not None and n0 is not None else None})
    pods=[]
    for name,v in pod_samples.items():
        group='envoy' if name.startswith('envoy-gateway-system/envoy-infra-gateway-public-gateway-') else 'backend' if name.startswith('platform-test/bench-api-') else 'other'
        pods.append({'pod':name,'group':group,'cpu_avg_m':quant(v['cpu_m'],statistics.mean),'cpu_max_m':quant(v['cpu_m']),'mem_max_mib':quant(v['mem_mib'])})
    docker=[]
    for name,v in dock_samples.items():
        docker.append({'node':name,'cpu_avg_pct':quant(v['cpu_pct'],statistics.mean),'cpu_peak_pct':quant(v['cpu_pct']),'mem_peak_mib':quant(v['mem_mib']),
          'net_rx_delta_mib':round(max(v['net_rx_mib'])-min(v['net_rx_mib']),2) if len(v['net_rx_mib'])>=2 else None,
          'net_tx_delta_mib':round(max(v['net_tx_mib'])-min(v['net_tx_mib']),2) if len(v['net_tx_mib'])>=2 else None})
    return {'samples':sample_count,'host_cpu_max_pct':quant(host_cpu),'host_cpu_avg_pct':quant(host_cpu,statistics.mean),'host_load1_max':quant(host_load),'host_used_mem_peak_mib':quant(host_mem_used),'pods':pods,'docker':docker,'throttling':throttling,'nodes':node_samples}

def fmt(v,places=2):
    return 'N/A' if v is None else f'{v:.{places}f}' if isinstance(v,float) else str(v)

def csvwrite(path,rows,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def generate(root):
    root=Path(root)
    allrows=[];podrows=[];noderows=[];thrrows=[]
    for case in sorted((root/'cases').glob('*')):
        if not (case/'run.json').exists():continue
        j=json.loads((case/'run.json').read_text());s=parse_hey(case/'hey.txt');r=stats_resources(case)
        public=[x for x in r['pods'] if x['group']=='envoy'];backend=[x for x in r['pods'] if x['group']=='backend']
        row={'id':j['id'],'path':j['path'],'concurrency':j['concurrency'],'repeat':j['repeat'],'elapsed_s':round(j['elapsed'],2),
          'run_exit_code':j['returncode'],**{k:v for k,v in s.items() if k!='status'},'failure_pct':count_failure_pct(s),'http_status':json.dumps(s['status'],sort_keys=True),
          'resource_samples':r['samples'], 'host_cpu_avg_pct':r['host_cpu_avg_pct'], 'host_cpu_peak_pct':r['host_cpu_max_pct'],
          'host_load1_peak':r['host_load1_max'],'host_mem_peak_mib':r['host_used_mem_peak_mib'],
          'envoy_cpu_peak_m':quant([x['cpu_max_m'] for x in public if x['cpu_max_m'] is not None]),
          'envoy_cpu_sum_avg_m':round(sum(x['cpu_avg_m'] for x in public if x['cpu_avg_m'] is not None),3) if public else None,
          'envoy_mem_sum_peak_mib':round(sum(x['mem_max_mib'] for x in public if x['mem_max_mib'] is not None),3) if public else None,
          'backend_cpu_sum_avg_m':round(sum(x['cpu_avg_m'] for x in backend if x['cpu_avg_m'] is not None),3) if backend else None,
          'backend_mem_sum_peak_mib':round(sum(x['mem_max_mib'] for x in backend if x['mem_max_mib'] is not None),3) if backend else None,
          'node_throttled_s_sum':round(sum(x['throttled_s'] for x in r['throttling']),3),
          'node_throttled_count_sum':sum(x['nr_throttled'] for x in r['throttling'] if x['nr_throttled'] is not None)}
        # Use Prometheus as fallback when kubectl top has no pod samples; preserve measured provenance.
        prom_path=root/'prometheus'/f"{j['id']}.json"
        if prom_path.exists():
            try:
                prom=json.loads(prom_path.read_text())
                def pm(key,kind='avg'):
                    vals=[float(v) for metric in prom.get('series',{}).get(key,[]) for t,v in metric.get('points',[]) if v is not None]
                    return (statistics.mean(vals) if kind=='avg' else max(vals)) if vals else None
                row['prom_envoy_rps_avg']=pm('envoy_downstream_rps')
                row['prom_envoy_pod_cpu_m_avg']=pm('envoy_pod_cpu_cores')*1000 if pm('envoy_pod_cpu_cores') is not None else None
                row['prom_envoy_pod_mem_peak_mib']=pm('envoy_pod_memory_bytes','peak')/1024**2 if pm('envoy_pod_memory_bytes','peak') is not None else None
                row['prom_backend_pod_cpu_m_avg']=pm('backend_pod_cpu_cores')*1000 if pm('backend_pod_cpu_cores') is not None else None
                row['prom_backend_pod_mem_peak_mib']=pm('backend_pod_memory_bytes','peak')/1024**2 if pm('backend_pod_memory_bytes','peak') is not None else None
                row['prom_envoy_connections_peak']=pm('envoy_active_connections','peak')
                row['prom_envoy_5xx_rps_avg']=pm('envoy_upstream_5xx_rps')
                row['prom_cpu_throttle_periods_rate']=pm('envoy_pod_cpu_throttle_rps')
                if row['envoy_cpu_sum_avg_m'] is None and row['prom_envoy_pod_cpu_m_avg'] is not None:row['envoy_cpu_sum_avg_m']=round(row['prom_envoy_pod_cpu_m_avg'],2)
                if row['envoy_mem_sum_peak_mib'] is None and row['prom_envoy_pod_mem_peak_mib'] is not None:row['envoy_mem_sum_peak_mib']=round(row['prom_envoy_pod_mem_peak_mib'],2)
                if row['backend_cpu_sum_avg_m'] is None and row['prom_backend_pod_cpu_m_avg'] is not None:row['backend_cpu_sum_avg_m']=round(row['prom_backend_pod_cpu_m_avg'],2)
                if row['backend_mem_sum_peak_mib'] is None and row['prom_backend_pod_mem_peak_mib'] is not None:row['backend_mem_sum_peak_mib']=round(row['prom_backend_pod_mem_peak_mib'],2)
            except (OSError,ValueError,TypeError,ZeroDivisionError) as e:
                row['prometheus_parse_error']=str(e)
        allrows.append(row)
        for p in r['pods']:podrows.append({'case':j['id'],**p})
        for d in r['docker']:noderows.append({'case':j['id'],**d})
        for d in r['throttling']:thrrows.append({'case':j['id'],**d})
    if not allrows:raise SystemExit('No completed run cases found')
    csvwrite(root/'summary.csv',allrows,list(allrows[0]))
    if podrows:csvwrite(root/'pod-resources.csv',podrows,list(podrows[0]))
    if noderows:csvwrite(root/'docker-node-resources.csv',noderows,list(noderows[0]))
    if thrrows:csvwrite(root/'cpu-throttling.csv',thrrows,list(thrrows[0]))
    bypair=defaultdict(dict)
    for row in allrows:bypair[(row['concurrency'],row['repeat'])][row['path']]=row
    comparisons=[]
    for (c,rep),pair in sorted(bypair.items()):
        a,b=pair.get('direct'),pair.get('envoy')
        if a is None or b is None:continue
        comparisons.append({'concurrency':c,'repeat':rep,'direct_rps':a['rps'],'envoy_rps':b['rps'],
          'envoy_to_direct_rps_pct':round(100*b['rps']/a['rps'],2) if a['rps'] and b['rps'] is not None else None,
          'direct_p95_ms':a['p95_ms'],'envoy_p95_ms':b['p95_ms'],
          'direct_p99_ms':a['p99_ms'],'envoy_p99_ms':b['p99_ms'],
          'p99_delta_ms':round(b['p99_ms']-a['p99_ms'],3) if a['p99_ms'] is not None and b['p99_ms'] is not None else None,
          'direct_fail_pct':a['failure_pct'],'envoy_fail_pct':b['failure_pct']})
    if comparisons:csvwrite(root/'comparison.csv',comparisons,list(comparisons[0]))
    lines=['# Envoy Gateway — High Load Benchmark Report','',f'Source: `{root}`','',
      '**Important:** these are measurements on the kind VM, not independently verified production capacity. Direct and Envoy paths differ in network hops.','',
      '## Run-level results','',
      '| Case | RPS | p50 ms | p95 ms | p99 ms | HTTP 200 | Non-200 | Transport errors | Failure % | Host CPU peak % | Envoy CPU avg sum (m) | Throttling s (sum, nodes) |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in allrows:
        lines.append('| '+ ' | '.join(map(fmt,[r['id'],r['rps'],r['p50_ms'],r['p95_ms'],r['p99_ms'],r['http_200'],r['http_non200'],r['transport_errors'],r['failure_pct'],r['host_cpu_peak_pct'],r['envoy_cpu_sum_avg_m'],r['node_throttled_s_sum']]))+' |')
    lines.extend(['','## Paired Direct vs Envoy','',
      '| Concurrency | Repeat | Direct RPS | Envoy RPS | Envoy / Direct % | Direct p99 ms | Envoy p99 ms | p99 delta ms | Envoy failure % |',
      '|---:|---:|---:|---:|---:|---:|---:|---:|---:|'])
    for r in comparisons:
        lines.append('| '+' | '.join(map(fmt,[r[k] for k in ['concurrency','repeat','direct_rps','envoy_rps','envoy_to_direct_rps_pct','direct_p99_ms','envoy_p99_ms','p99_delta_ms','envoy_fail_pct']]))+' |')
    lines.extend(['','## Median across repetitions','',
     '| Concurrency | Direct RPS median | Envoy RPS median | RPS ratio median % | Direct p99 median ms | Envoy p99 median ms |',
     '|---:|---:|---:|---:|---:|---:|'])
    byc=defaultdict(list)
    for c in comparisons:byc[c['concurrency']].append(c)
    for c,pairs in sorted(byc.items()):
        def median(key):
            v=[x[key] for x in pairs if x[key] is not None]
            return round(statistics.median(v),3) if v else None
        lines.append('| '+' | '.join(map(fmt,[c,median('direct_rps'),median('envoy_rps'),median('envoy_to_direct_rps_pct'),median('direct_p99_ms'),median('envoy_p99_ms')]))+' |')
    lines += ['', '## Resource data files', '',
      '- `pod-resources.csv`: peak and average CPU/memory per Pod per case. CPU in millicores.',
      '- `docker-node-resources.csv`: Docker kind node container CPU%, memory and sampled network I/O.',
      '- `cpu-throttling.csv`: per-node cgroup throttled CPU time and count between case start/end.',
      '- `cases/<case>/resources.jsonl`: raw timestamped host, Docker and Kubernetes samples.',
      '- `snapshot/`: initial Kubernetes and Docker resource/configuration state.',
      '', '## Interpretation / known limitations', '',
      '- CPU throttling seconds are **summed across kind node cgroups**, not a single wall-clock stall; do not interpret directly as user-facing latency.',
      '- `docker stats` CPU% is per logical CPU: 100% ≈ one CPU core. Node quotas require a separate comparison with Docker inspect.',
      '- `kubectl top` samples are not an exact total CPU consumption measurement; unavailable metrics are N/A, never zero.',
      '- Prometheus enrichment is optional via scripts/prom_enrich.py; missing data stays N/A. Queries use 1m rate windows.',
      '- `hey` uses a concurrency-driven workload; this is **not** a controlled open-loop fixed-QPS test.',
      '- Same-host kind benchmarking shares physical host CPU and I/O. For production capacity, use external load generator, pin workloads and repeat.',
      '- Review `STOP_REASON.txt` if present; failed cases must not be used to claim sustainable peak capacity.',
      '']
    (root/'report.md').write_text('\n'.join(lines))
    print(f'REPORT: {root}/report.md\nCSV: {root}/summary.csv, comparison.csv, pod-resources.csv, docker-node-resources.csv, cpu-throttling.csv',flush=True)

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python3 scripts/report.py bench-heavy-results-YYYYmmdd-HHMMSS')
    generate(Path(sys.argv[1]).expanduser())
