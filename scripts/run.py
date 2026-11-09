#!/usr/bin/env python3
"""Controlled high-load Envoy vs direct NodePort benchmark. Python stdlib only.
Run from Ubuntu VM with kubectl, docker, hey and curl installed.
"""
import argparse, datetime as dt, json, os, re, shlex, shutil, signal, statistics, subprocess, sys, threading, time
from pathlib import Path

NODES = ['envoy-lab-control-plane','envoy-lab-worker','envoy-lab-worker2','envoy-lab-worker3','envoy-lab-worker4','envoy-lab-worker5']
PROFILES = {'quick':[100,250,500], 'heavy':[250,500,1000,2000,4000], 'extreme':[1000,2000,4000,8000], 'soak':[500], 'burst':[500,2000,500,4000], 'saturation':[500,1000,2000,4000,6000,8000]}

def command(args, timeout=20, check=False, env=None):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, env=env)
        if check and p.returncode: raise RuntimeError(f"{' '.join(args)}\n{p.stderr.strip()}")
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        if check: raise RuntimeError(str(e)) from e
        return '',str(e),1

def kube_json(args):
    out,err,rc=command(['kubectl',*args,'-o','json'],timeout=20,check=True)
    return json.loads(out)

def get_service(namespace,selector=None,name=None):
    if name:
        return kube_json(['get','svc',name,'-n',namespace])
    services=kube_json(['get','svc','-n',namespace,'-l',selector])['items']
    if len(services)!=1: raise RuntimeError(f'Expected exactly one service for {selector}, got {len(services)}')
    return services[0]

def nodeport(svc,port=80):
    found=[p.get('nodePort') for p in svc['spec']['ports'] if p['port']==port]
    if len(found)!=1 or not found[0]: raise RuntimeError(f"Missing NodePort on {svc['metadata']['name']} port {port}")
    return found[0]

def parse_cpu_unit(s):
    s=s.strip()
    if s.endswith('m'): return float(s[:-1])/1000
    if s.endswith('n'): return float(s[:-1])/1e9
    return float(s)

def save_snapshot(out):
    cmds={
       'nodes.json':['kubectl','get','nodes','-o','json'],
       'gateway.json':['kubectl','get','gateways','-A','-o','json'],
       'httproutes.json':['kubectl','get','httproutes','-A','-o','json'],
       'envoy-pods.json':['kubectl','get','pods','-n','envoy-gateway-system','-o','json'],
       'backend-pods.json':['kubectl','get','pods','-n','platform-test','-o','json'],
       'services.txt':['kubectl','get','svc','-A','-o','wide'],
       'docker-limits.json':['docker','inspect',*NODES],
    }
    dest=out/'snapshot';dest.mkdir(parents=True,exist_ok=True)
    for name,cmd in cmds.items():
        stdout,stderr,rc=command(cmd,timeout=30)
        (dest/name).write_text(stdout if rc==0 else f'ERROR {rc}: {stderr}\n')

def cgroup_stats():
    vals={}
    for n in NODES:
        o,err,rc=command(['docker','exec',n,'cat','/sys/fs/cgroup/cpu.stat'],timeout=5)
        if rc==0:
            vals[n]={k:int(v) for k,v in (line.split() for line in o.splitlines() if len(line.split())==2) if v.isdigit()}
    return vals

def host_stats(last_cpu=None):
    try:
        with open('/proc/stat') as f:
            cpu=[int(x) for x in f.readline().split()[1:]]
        idle=cpu[3]+(cpu[4] if len(cpu)>4 else 0)
        total=sum(cpu)
        pct=None
        if last_cpu:
            denom=total-last_cpu[0]
            if denom>0:pct=round(100*(1-(idle-last_cpu[1])/denom),2)
        with open('/proc/meminfo') as f:mem=dict((a.strip(),int(re.search(r'\d+',b).group())) for a,b in (l.split(':',1) for l in f) if re.search(r'\d+',b))
        load=os.getloadavg()
        return {'cpu_util_pct':pct,'load1':load[0], 'load5':load[1], 'mem_total_kib':mem.get('MemTotal'), 'mem_available_kib':mem.get('MemAvailable')},(total,idle)
    except Exception as e:return {'error':str(e)},last_cpu

class Sampler:
    def __init__(self,casepath,interval):
        self.casepath=casepath;self.interval=interval;self.stop=threading.Event();self.thread=None
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=15)
    def run(self):
        previous=None
        with (self.casepath/'resources.jsonl').open('w',buffering=1) as f:
            while not self.stop.is_set():
                started=time.monotonic()
                entry={'timestamp':dt.datetime.now(dt.timezone.utc).isoformat()}
                entry['host'],previous=host_stats(previous)
                queries={
                   'docker':['docker','stats','--no-stream','--format','{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}',*NODES],
                   'pods':['kubectl','top','pods','-A','--no-headers'],
                   'nodes':['kubectl','top','nodes','--no-headers'],
                }
                for name,cmd in queries.items():
                    out,err,rc=command(cmd,timeout=12)
                    entry[name]=out if rc==0 else ''
                    if rc:entry[name+'_error']=err[:250]
                f.write(json.dumps(entry,ensure_ascii=False)+'\n')
                self.stop.wait(max(0.1,self.interval-(time.monotonic()-started)))

def smoke(url,hostname=None):
    args=['curl','--noproxy','*','--connect-timeout','3','--max-time','8','-sS','-o','/dev/null','-w','%{http_code}']
    if hostname:args+=['-H','Host: '+hostname]
    out,err,rc=command([*args,url],timeout=11)
    if rc or out!='200':raise RuntimeError(f'Smoke failed: url={url} host={hostname} status={out} error={err}')

def main():
    p=argparse.ArgumentParser(description='Sequential high-load benchmark, with per-case resource telemetry and safety stop')
    p.add_argument('--profile', choices=list(PROFILES),default='heavy')
    p.add_argument('--node-ip',default=os.getenv('NODE_IP','172.18.0.7'))
    p.add_argument('--hostname',default='httpbin.dev.local')
    p.add_argument('--duration',type=int,default=None,help='seconds for each case; defaults 60 heavy, 120 extreme, 900 soak')
    p.add_argument('--repeats',type=int,default=None,help='default 3 heavy/quick, 2 extreme, 1 soak')
    p.add_argument('--interval',type=int,default=5,help='resource sample interval seconds')
    p.add_argument('--cooldown',type=int,default=15)
    p.add_argument('--max-failure-pct',type=float,default=2.0)
    p.add_argument('--allow-extreme',action='store_true')
    p.add_argument('--out',default=None)
    p.add_argument('--concurrencies',default=None,help='comma-separated concurrency sequence, e.g. 100,500,1000,2000')
    p.add_argument('--no-keepalive',action='store_true',help='benchmark new TCP connections per request')
    p.add_argument('--skip-prometheus',action='store_true',help='do not attempt Prometheus enrichment')
    args=p.parse_args()
    if args.profile in ('extreme','saturation') and not args.allow_extreme:p.error('Extremely high concurrency needs --allow-extreme')
    args.duration=args.duration or (900 if args.profile=='soak' else 120 if args.profile=='extreme' else 60)
    args.repeats=args.repeats or (1 if args.profile=='soak' else 2 if args.profile=='extreme' else 3)
    if args.concurrencies:
        try: levels=[int(x.strip()) for x in args.concurrencies.split(',')]
        except ValueError: p.error('Invalid --concurrencies')
        if not levels or any(x<1 or x>10000 for x in levels):p.error('concurrencies must be 1..10000')
    else: levels=PROFILES[args.profile]
    if max(levels)>4000 and not args.allow_extreme:p.error('Above 4000 concurrency requires --allow-extreme')
    if not(10<=args.duration<=3600 and 1<=args.repeats<=10 and 2<=args.interval<=60 and 0<=args.cooldown<=600 and 0<=args.max_failure_pct<=100):p.error('Invalid numeric parameters')
    for exe in ['kubectl','docker','curl','hey']:
        if not shutil.which(exe):raise SystemExit(f'Missing command: {exe}')
    public=get_service('envoy-gateway-system',selector='gateway.envoyproxy.io/owning-gateway-name=public-gateway')
    direct=get_service('platform-test',name='bench-direct')
    public_port=nodeport(public);direct_port=nodeport(direct)
    env_url=f'http://{args.node_ip}:{public_port}/bench'
    direct_url=f'http://{args.node_ip}:{direct_port}/bench'
    print('Public:',env_url,'\nDirect:',direct_url,'\nRunning smoke tests...',flush=True)
    smoke(direct_url);smoke(env_url,args.hostname)
    # Verify no known rollout problems before benchmarking
    for d in ['bench-api']:
        dep=kube_json(['get','deployment',d,'-n','platform-test'])
        if dep['status'].get('readyReplicas',0)<dep['spec']['replicas']:
            raise SystemExit(f'{d} is not fully Ready')
    proxies=kube_json(['get','deployments','-n','envoy-gateway-system'])['items']
    pub=[x for x in proxies if x['metadata']['name'].startswith('envoy-infra-gateway-public-gateway-')]
    if not pub or any(x['status'].get('readyReplicas',0)<x['spec']['replicas'] for x in pub):raise SystemExit('Public Envoy deployment is not fully Ready')
    out=Path(args.out or f'bench-heavy-results-{dt.datetime.now().strftime("%Y%m%d-%H%M%S")}').resolve()
    if out.exists():raise SystemExit(f'Output directory already exists: {out}')
    out.mkdir(parents=True)
    meta={'profile':args.profile,'node_ip':args.node_ip,'hostname':args.hostname,'duration':args.duration,'repeats':args.repeats,'concurrencies':levels, 'keepalive':not args.no_keepalive, 'max_failure_pct':args.max_failure_pct, 'sample_interval':args.interval,'public_url':env_url,'direct_url':direct_url,'public_service':public['metadata']['name'],'external_traffic_policy':public['spec'].get('externalTrafficPolicy','Cluster'),'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'tool':'hey'}
    (out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(f'Output directory: {out}',flush=True)
    save_snapshot(out)
    def finalize():
        if not args.skip_prometheus:
            enrich_script=Path(__file__).with_name('prom_enrich.py')
            result=subprocess.run([sys.executable,str(enrich_script),str(out)],capture_output=True,text=True,timeout=240)
            (out/'prometheus-enrich.log').write_text(result.stdout+'\n'+result.stderr)
            if result.returncode:print('Prometheus enrichment unavailable; see prometheus-enrich.log',flush=True)
        from report import generate
        generate(out)
        dashboard=Path(__file__).with_name('dashboard.py')
        result=subprocess.run([sys.executable,str(dashboard),str(out)],capture_output=True,text=True,timeout=45)
        (out/'dashboard-build.log').write_text(result.stdout+'\n'+result.stderr)
        if result.returncode:print('HTML dashboard generation failed; see dashboard-build.log',flush=True)

    # Warm up both paths without mixing warm-up samples into measured runs.
    for path,uri in [('direct',direct_url),('envoy',env_url)]:
        cmd=['hey','-z','20s','-c','50','-t','15']
        if path=='envoy':cmd+=['-host',args.hostname]
        cmd.append(uri)
        e=os.environ.copy()
        for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:e.pop(k,None)
        print(f'Warm-up {path}: 20s, concurrency 50',flush=True)
        with (out/f'warmup-{path}.txt').open('w') as f:
            warm=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=e,timeout=60)
        if warm.returncode!=0:raise RuntimeError(f'Warm-up {path} failed: inspect warmup-{path}.txt')
    run_ids=[]
    # stagger and reverse pair order every repeat to reduce systematic time bias
    for c in levels:
        for rep in range(1,args.repeats+1):
            paths=['direct','envoy'] if rep%2 else ['envoy','direct']
            for path in paths:
                run_id=f'{path}-c{c}-r{rep}'
                casepath=out/'cases'/run_id;casepath.mkdir(parents=True)
                uri=direct_url if path=='direct' else env_url
                heyargs=['hey','-z',f'{args.duration}s','-c',str(c),'-t','15']
                if args.no_keepalive:heyargs.append('-disable-keepalive')
                if path=='envoy':heyargs+=['-host',args.hostname]
                heyargs.append(uri)
                print(f'\n>>> {run_id}: {args.duration}s',flush=True)
                sampler=Sampler(casepath,args.interval)
                startstats=cgroup_stats();sampler.start();start=time.monotonic();started_utc=dt.datetime.now(dt.timezone.utc).isoformat()
                environ=os.environ.copy()
                for name in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:environ.pop(name,None)
                try:
                    with (casepath/'hey.txt').open('w') as f:
                        proc=subprocess.run(heyargs,stdout=f,stderr=subprocess.STDOUT,timeout=args.duration+45,env=environ)
                        rc=proc.returncode
                except subprocess.TimeoutExpired:
                    rc=124
                    with (casepath/'hey.txt').open('a') as f:f.write('\n[RUNNER] hey timed out\n')
                except KeyboardInterrupt:
                    print('Interrupted. Saving partial report.',file=sys.stderr)
                    rc=130
                finally:
                    sampler.close()
                endstats=cgroup_stats()
                elapsed=time.monotonic()-start
                ended_utc=dt.datetime.now(dt.timezone.utc).isoformat()
                (casepath/'run.json').write_text(json.dumps({'id':run_id,'path':path,'concurrency':c,'repeat':rep,'duration_requested':args.duration,'start_utc':started_utc,'end_utc':ended_utc,'elapsed':elapsed,'returncode':rc,'cgroup_before':startstats,'cgroup_after':endstats},indent=2)+'\n')
                run_ids.append(run_id)
                from report import parse_hey, count_failure_pct
                stats=parse_hey(casepath/'hey.txt')
                pct=count_failure_pct(stats)
                print(f'RPS={stats.get("rps")} p99(ms)={stats.get("p99_ms")} HTTP200={stats.get("http_200")} failures={pct if pct is not None else "UNKNOWN"}% rc={rc}',flush=True)
                if rc or pct is None or pct>args.max_failure_pct:
                    reason=f'Stopped on {run_id}: rc={rc}, failure={pct}%, threshold={args.max_failure_pct}%'
                    (out/'STOP_REASON.txt').write_text(reason+'\n')
                    print('SAFETY STOP:',reason,flush=True)
                    finalize()
                    return 2
                if args.cooldown:
                    print(f'Cooldown {args.cooldown}s...',flush=True)
                    time.sleep(args.cooldown)
    finalize()
    print('\nCOMPLETE:',out,flush=True)
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (RuntimeError,KeyboardInterrupt) as e:
        print('ERROR:',e,file=sys.stderr)
        sys.exit(1)
