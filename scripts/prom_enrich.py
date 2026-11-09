#!/usr/bin/env python3
"""Historical Prometheus enrichment of benchmark cases; stdlib-only.
Uses local Prometheus HTTP URL or a temporary kubectl port-forward.
"""
import argparse, datetime as dt, json, os, socket, subprocess, time, urllib.parse, urllib.request
from pathlib import Path

QUERIES = {
 'envoy_downstream_rps': 'sum(rate(envoy_http_downstream_rq_total[1m]))',
 'envoy_upstream_rps': 'sum(rate(envoy_cluster_upstream_rq_total[1m]))',
 'envoy_upstream_5xx_rps': 'sum(rate(envoy_cluster_upstream_rq_5xx[1m]))',
 'envoy_active_connections': 'sum(envoy_http_downstream_cx_active)',
 'envoy_upstream_active_connections': 'sum(envoy_cluster_upstream_cx_active)',
 'envoy_memory_bytes': 'sum(envoy_server_memory_allocated)',
 'envoy_retries_rps': 'sum(rate(envoy_cluster_upstream_rq_retry[1m]))',
 'envoy_pod_cpu_cores': 'sum(rate(container_cpu_usage_seconds_total{namespace="envoy-gateway-system",pod=~"envoy-infra-gateway-public-gateway-.*",container="envoy"}[1m]))',
 'envoy_pod_memory_bytes': 'sum(container_memory_working_set_bytes{namespace="envoy-gateway-system",pod=~"envoy-infra-gateway-public-gateway-.*",container="envoy"})',
 'backend_pod_cpu_cores': 'sum(rate(container_cpu_usage_seconds_total{namespace="platform-test",pod=~"bench-api-.*",container!="POD"}[1m]))',
 'backend_pod_memory_bytes': 'sum(container_memory_working_set_bytes{namespace="platform-test",pod=~"bench-api-.*",container!="POD"})',
 'envoy_pod_cpu_throttle_rps': 'sum(rate(container_cpu_cfs_throttled_periods_total{namespace="envoy-gateway-system",pod=~"envoy-infra-gateway-public-gateway-.*"}[1m]))',
 'envoy_pod_cpu_per_pod': 'sum by(pod) (rate(container_cpu_usage_seconds_total{namespace="envoy-gateway-system",pod=~"envoy-infra-gateway-public-gateway-.*",container="envoy"}[1m]))',
 'backend_pod_cpu_per_pod': 'sum by(pod) (rate(container_cpu_usage_seconds_total{namespace="platform-test",pod=~"bench-api-.*",container!="POD"}[1m]))',
}

def request(base, path, qs=None, timeout=12):
    url=base.rstrip('/')+'/'+path.lstrip('/')
    if qs:url+='?'+urllib.parse.urlencode(qs)
    req=urllib.request.Request(url, headers={'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.load(r)

def parse_utc(v):
    return dt.datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()

def times(case):
    run=json.loads((case/'run.json').read_text())
    if run.get('start_utc') and run.get('end_utc'):
        return parse_utc(run['start_utc']),parse_utc(run['end_utc'])
    f=case/'resources.jsonl'; stamps=[]
    if f.exists():
        for line in f.read_text(errors='replace').splitlines():
            try:stamps.append(parse_utc(json.loads(line)['timestamp']))
            except (KeyError,ValueError,json.JSONDecodeError):pass
    if not stamps:return None
    # Older runner did not store start/end UTC; samples under-cover final seconds.
    return min(stamps),max(stamps)

def port_forward(namespace,service):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    p=subprocess.Popen(['kubectl','-n',namespace,'port-forward',f'svc/{service}',f'{port}:80','--address','127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    base=f'http://127.0.0.1:{port}'
    for _ in range(35):
        if p.poll() is not None:raise RuntimeError(f'port-forward exited: {p.stderr.read().decode(errors="replace")[-500:]}')
        try:
            if request(base,'api/v1/status/buildinfo').get('status')=='success':return base,p
        except Exception:time.sleep(.25)
    p.terminate();raise RuntimeError('Prometheus port-forward is not responding')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('results',type=Path)
    ap.add_argument('--prom-url',default=os.getenv('PROMETHEUS_URL',''))
    ap.add_argument('--namespace',default='monitoring')
    ap.add_argument('--service',default='prometheus')
    ap.add_argument('--step',type=int,default=10)
    a=ap.parse_args()
    root=a.results.expanduser().resolve();cases=sorted((root/'cases').glob('*'))
    if not cases:raise SystemExit('No case folders')
    pf=None
    try:
        if a.prom_url:base=a.prom_url
        else:base,pf=port_forward(a.namespace,a.service)
        outdir=root/'prometheus';outdir.mkdir(exist_ok=True)
        try:
            targets=request(base,'api/v1/targets',{'state':'active'})
            small=[]
            for t in targets.get('data',{}).get('activeTargets',[]):
                small.append({'job':t.get('labels',{}).get('job'),'instance':t.get('labels',{}).get('instance'), 'health':t.get('health'),'lastError':t.get('lastError','')})
            (outdir/'targets.json').write_text(json.dumps(small,indent=2))
            print('Prometheus targets:',len(small),'UP:',sum(t['health']=='up' for t in small))
        except Exception as e: print('Targets unavailable:',e)
        details=[]
        for case in cases:
            window=times(case)
            if not window:
                print('Skip no UTC timestamps:',case.name);continue
            start,end=window
            # add 30s margin for scrape/rate smoothing; report marks inference
            start-=30;end+=30
            series={};errors={}
            for name,promql in QUERIES.items():
                try:
                    response=request(base,'api/v1/query_range',{'query':promql,'start':f'{start:.3f}','end':f'{end:.3f}','step':a.step})
                    if response.get('status')!='success':raise RuntimeError(response.get('error','query failed'))
                    results=response.get('data',{}).get('result',[])
                    series[name]=[{'labels':x.get('metric',{}),'points':[[float(t),float(v) if v not in ('NaN','+Inf','-Inf') else None] for t,v in x.get('values',[])]} for x in results]
                except Exception as e:errors[name]=str(e)
            payload={'case':case.name,'time_source':'run.json' if json.loads((case/'run.json').read_text()).get('start_utc') else 'inferred from resources.jsonl','window_start':start,'window_end':end,'promql':QUERIES,'series':series,'errors':errors}
            (outdir/f'{case.name}.json').write_text(json.dumps(payload,indent=2))
            present=sum(bool(v) for v in series.values())
            print(case.name,':',present,'metric queries with data,',len(errors),'errors')
            details.append({'case':case.name,'available_metrics':[k for k,v in series.items() if v], 'query_errors':errors})
        (outdir/'coverage.json').write_text(json.dumps(details,indent=2))
        print('Prometheus results:',outdir)
    finally:
        if pf:
            pf.terminate()
            try:pf.wait(timeout=4)
            except subprocess.TimeoutExpired:pf.kill()

if __name__=='__main__':main()
