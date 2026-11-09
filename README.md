# Envoy Gateway — heavy benchmark kit (kind, 6 nodes)

## Safety and intent

Run **only on the dedicated lab VM**. Very high concurrency can overload the VM, Docker bridge/NAT, conntrack, kube-proxy and load generator as well as Envoy. Avoid on shared production nodes. Does not modify Kubernetes configuration. Existing `platform-test/bench-direct` and `platform-test/bench-through-envoy` must already be deployed and healthy. HTTP route must match host `httpbin.dev.local`, path `/bench`.

Benchmark order: paired Direct Backend NodePort vs Envoy Public Gateway NodePort. A 60-second default run at each concurrency is repeated three times (order reversed every second repetition), with resource sampling and a 15-second cooldown. This long run can be interrupted with Ctrl+C; interrupted results should not be presented as final capacity.

**Prerequisites**: `python3`, `kubectl`, `docker`, `hey`, `curl`; Kubernetes metrics-server for `kubectl top`; proper Docker socket access. Run as root on the VM, with kind context `kind-envoy-lab`. Host's HCM proxy is unset **only for hey** to ensure local traffic does not traverse proxy.

```bash
kubectl config current-context
kubectl get gateway -A
kubectl get pods -n envoy-gateway-system -o wide
kubectl get pods -n platform-test -l app=bench-api -o wide
kubectl top pods -n envoy-gateway-system
```

**Important:** Public Envoy Proxy previously ran on Worker 2 + Worker 3; before capacity-grade benchmarking fix placement to Gateway Workers 1/2 by editing the authoritative `EnvoyProxy` resource (not Deployment). Ensure NodePort connectivity and actual two proxy endpoints. With `externalTrafficPolicy: Cluster` all nodes can forward, but additional network hop remains possible. Use one fixed node IP for all tests, and record traffic policy.

## Commands

Extract the package to `/root/envoy-heavy-benchmark/` and run:

```bash
cd /root/envoy-heavy-benchmark
python3 scripts/run.py --profile quick --node-ip 172.18.0.7 --duration 30 --repeats 1
python3 scripts/run.py --profile heavy --node-ip 172.18.0.7
# Opt-in: 8000 concurrent connections. Run only after checking host and service limits.
python3 scripts/run.py --profile extreme --node-ip 172.18.0.7 --allow-extreme
# Optional 15-minute soak test, sequential direct then Envoy
python3 scripts/run.py --profile soak --node-ip 172.18.0.7 --duration 900
```

Heavy profile cases are 250, 500, 1000, 2000, 4000 concurrency, each Direct and Envoy, three repetitions, 60 seconds each, with cooldowns. Expected time is over 30 minutes. If throughput stops rising, latency and failures spike or load-generator CPU saturates, stop instead of increasing concurrency.

Every case automatically samples: `docker stats` for all 6 kind nodes; `kubectl top pods -A` for Envoy and backend; `kubectl top nodes`; VM host `/proc/stat`, `/proc/meminfo` and load average; cgroup CPU throttle before/after each case. Some metric series may be missing if metrics-server hasn't collected them yet. Monitoring tools themselves add slight overhead.

At the end, reports are automatically generated. To regenerate or update reports:

```bash
RESULT_DIR=$(ls -dt bench-heavy-results-* | head -1)
python3 scripts/report.py "$RESULT_DIR"
cat "$RESULT_DIR/report.md"
column -s, -t < "$RESULT_DIR/summary.csv"
tar -czf "${RESULT_DIR}.tar.gz" "$RESULT_DIR"
```

Files:
- `report.md`: measured RPS/latency/status/error and median comparisons.
- `summary.csv`: per-case measurements + resource aggregates.
- `comparison.csv`: paired Direct vs Envoy.
- `pod-resources.csv`: CPU/memory per Pod.
- `docker-node-resources.csv`: per-kind node Docker CPU%, memory and sampled network transfer.
- `cpu-throttling.csv`: cgroup throttling by node.
- `cases/<case>/hey.txt`: original load-generator output.
- `cases/<case>/resources.jsonl`: raw samples including host utilization.
- `snapshot/`: Kubernetes objects and Docker resource settings before run.
- `STOP_REASON.txt`: reason if safety stop occurred.

## Test profiles

| Profile | Concurrent clients | Duration per case | Repetitions | When to use |
|---|---|---|---|---|
| quick | 100, 250, 500 | 60s by default | 3 | smoke and baseline |
| heavy | 250, 500, 1000, 2000, 4000 | 60s | 3 | high load saturation search |
| extreme | 1000, 2000, 4000, 8000 | 120s | 2 | optional stress, possible network/FD exhaustion |
| soak | 500 | 900s | 1 | prolonged memory/CPU stability |

The script automatically **stops further cases when failure percentage exceeds 2%, or hey exits with an error, or statistics are unavailable**. Lowering that guard requires intentional CLI override `--max-failure-pct`.

## How to evaluate

1. Compare each concurrency by p95/p99 and error percentage, not RPS alone.
2. Verify that the load generator has capacity before attributing lower RPS to Envoy.
3. Compare Envoy pod CPU total and per-node Docker CPU to the configured quotas; check throttling seconds/count per node.
4. Determine the last sustainable level with low errors, acceptable p99 and no resource saturation.
5. Re-test from a **separate load-generator VM** before using numbers for production capacity projections.

Use Grafana simultaneously to check Envoy per-Pod RPS, upstream latency, errors, connections, and Kubernetes CPU throttling. The kit collects host/kubectl/docker stats, not Prometheus time series automatically.
