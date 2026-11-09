# Envoy Gateway Benchmark v3 — Prometheus + Charts

**Target:** existing 6-node kind lab, Public Envoy Gateway NodePort and `platform-test/bench-direct` NodePort. Does not apply/change Kubernetes resources. Collection uses Prometheus already running in `monitoring`, no additional Prometheus installation. Only run intense tests in the isolated lab.

## Fixes over v2

- Prometheus `/api/v1/query_range` backfill for each case (HTTP request rate, connections, errors, upstream, Envoy memory and optional cAdvisor CPU/RAM), including historical v2 runs if retention still covers the run timestamps.
- Captures Prometheus `/api/v1/targets` health to distinguish no data from scrape failures.
- Offline `dashboard.html`: SVG charts for RPS, p99, errors, CPU/RAM, host utilization; comparison tables with individual cases; Prom metrics appendix.
- Separate CSVs and `report.md` retained. If `kubectl top` CPU is N/A, reports can use Prometheus cAdvisor metrics as fallback when available.
- `run.py` adds `--concurrencies` and `--no-keepalive`, plus burst and saturation profiles. Includes start/end UTC for new cases.

## Setup

```bash
cd /root
unzip envoy-benchmark-v3.zip
cd envoy-benchmark-v3
python3 -m py_compile scripts/*.py
kubectl config current-context  # expected kind-envoy-lab
kubectl -n monitoring get svc prometheus
kubectl -n envoy-gateway-system get pods -o wide
kubectl get pods -n platform-test -l app=bench-api -o wide
kubectl get httproute bench-through-envoy -n platform-test
```

Verify Prometheus has active Envoy and kubelet/cAdvisor scrape targets. Missing container CPU series means resource charts may rely on `kubectl top` and cgroup/Docker samples.

## Enrich the **existing v2** results immediately (no need to rerun)

```bash
cd /root/envoy-benchmark-v3
OLD=/root/envoy-audit-benchmark/bench-heavy-results-20261109-164617
python3 scripts/prom_enrich.py "$OLD"
python3 scripts/report.py "$OLD"
python3 scripts/dashboard.py "$OLD"
# Open the local static report on Windows using SCP:
# scp -P 2205 root@100.111.17.57:$OLD/dashboard.html .
```

If Prometheus retention has not expired, historical cases can be enriched using timestamps in `resources.jsonl`. **The old runner did not save exact start/end UTC**: these windows are inferred from available resource samples, so Prometheus rate estimates are approximate. No metric will be invented when unavailable.

## New scenarios

```bash
cd /root/envoy-benchmark-v3
# A 1-run verification, then check summary and chart before doing more
python3 scripts/run.py --profile quick --node-ip 172.18.0.7 --duration 30 --repeats 1

# Main capacity curve with 3 repeats per path, default 60 sec per case
python3 scripts/run.py --profile heavy --node-ip 172.18.0.7

# Step/load-unload burst (not fixed QPS)
python3 scripts/run.py --profile burst --node-ip 172.18.0.7 --duration 45 --repeats 2

# Controlled custom stress stages (requires opt-in over 4k concurrency)
python3 scripts/run.py --profile heavy --concurrencies 500,1000,2000,3000,4000 --node-ip 172.18.0.7 --duration 90 --repeats 3
python3 scripts/run.py --profile saturation --node-ip 172.18.0.7 --allow-extreme --duration 60 --repeats 1

# Connection churn: a new TCP connection per request (overhead may be huge)
python3 scripts/run.py --profile quick --node-ip 172.18.0.7 --duration 30 --repeats 1 --no-keepalive

# Long-running stability test
python3 scripts/run.py --profile soak --node-ip 172.18.0.7 --duration 900 --repeats 1
```

`run.py` performs HTTP 200 smoke tests, validates backend/Envoy deployments and aborts subsequent cases if failure rate > 2%, load generator fails, or output is unparseable. **It is not an in-flight emergency kill switch**; you must watch the node, available FD/conntrack, 5xx and load-generator CPU and stop if necessary. Run saturation only after lower stages are stable. All workloads are serial and may last a long time. Current NodePort `externalTrafficPolicy=Cluster` makes node choice less important for connectivity, but can add network hops; record it and keep it fixed.

## Prometheus connection

The collector defaults to a temporary loopback-only `kubectl -n monitoring port-forward svc/prometheus LOCALPORT:80` established **after** the cases. It uses the HTTP API and does not require exposing port 9090 publicly. Alternatively:

```bash
python3 scripts/prom_enrich.py "$OLD" --prom-url http://127.0.0.1:9090
```

`prometheus/targets.json` captures scrape target statuses. `prometheus/<case>.json` includes raw PromQL and time series, with empty data reported as unavailable (N/A). Because stats often use `rate(...[1m])`, short cases and close-spaced cases can have smoothing/overlap. Prometheus also needs to collect container metrics; installing Prometheus/Grafana alone is not proof those metrics exist.

## Report artifacts

```
bench-heavy-results-*/
  metadata.json
  snapshot/
  cases/<case>/hey.txt, run.json, resources.jsonl
  prometheus/targets.json, coverage.json, <case>.json
  summary.csv, comparison.csv, pod-resources.csv
  docker-node-resources.csv, cpu-throttling.csv
  report.md
  dashboard.html
```

The HTML file works offline (static SVG, no JS/CDN). Download with Windows PowerShell `scp -P 2205 root@100.111.17.57:/absolute/path/dashboard.html .` and open in browser.

## Interpret correctly

- `hey` is **closed-loop concurrency**, not guaranteed target QPS. Saturation can be in VM, Docker bridge, conntrack, kube-proxy, TLS, Nginx or client, not necessarily Envoy.
- Compare identical backend, connection reuse and network path in paired runs, ideally with 3 or more repetitions and external load generator.
- The v2 report showing 1,000,000 responses in each case reflects a fixed request-count run; inspect raw `hey.txt`, `run.json` and CLI command to verify actual run duration. A `Requests/sec` alone is insufficient for capacity claims.
- CPU use in millicores is not the same as allocated CPU quotas; quantify CPU throttling, Pod CPU limits and node cgroup limits independently.
- `envoy_downstream_rps` is an aggregate from any scraped Envoy proxies; it may include unrelated routes and may not exactly match client `hey` RPS. Use per-cluster/per-route labels when configured for production-quality results.
- Prometheus series may be absent (metrics not scraped, no cAdvisor exporter, retention elapsed) and are shown as N/A, never as zero.
