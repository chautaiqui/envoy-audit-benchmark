# Envoy Gateway — High Load Benchmark Report

Source: `bench-heavy-results-20261109-181026`

**Important:** these are measurements on the kind VM, not independently verified production capacity. Direct and Envoy paths differ in network hops.

## Run-level results

| Case | RPS | p50 ms | p95 ms | p99 ms | HTTP 200 | Non-200 | Transport errors | Failure % | Host CPU peak % | Envoy CPU avg sum (m) | Throttling s (sum, nodes) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| direct-c1000-r1 | 116263.49 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 41.43 | 1958.86 | 1.22 |
| direct-c2000-r1 | 81154.46 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 45.07 | 1606.21 | 0.00 |
| direct-c3000-r1 | 76846.98 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 45.40 | 2024.45 | 0.00 |
| direct-c4000-r1 | 71069.50 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 45.14 | 1831.12 | 0.00 |
| direct-c500-r1 | 141211.42 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 40.00 | 1469.85 | 0.00 |
| envoy-c1000-r1 | 46852.12 | N/A | N/A | N/A | 937875 | 0 | 0 | 0.00 | 36.47 | 2054.19 | 0.00 |
| envoy-c2000-r1 | 41260.74 | N/A | N/A | N/A | 826680 | 0 | 0 | 0.00 | 34.72 | 2030.21 | 0.00 |
| envoy-c3000-r1 | 40574.03 | N/A | N/A | N/A | 806512 | 7413 | 0 | 0.91 | 35.38 | 2199.35 | 0.00 |
| envoy-c4000-r1 | 44600.76 | N/A | N/A | N/A | 668233 | 228112 | 0 | 25.45 | 37.83 | 2272.73 | 0.00 |
| envoy-c500-r1 | 48747.48 | N/A | N/A | N/A | 975375 | 0 | 0 | 0.00 | 36.55 | 2182.86 | 0.00 |

## Paired Direct vs Envoy

| Concurrency | Repeat | Direct RPS | Envoy RPS | Envoy / Direct % | Direct p99 ms | Envoy p99 ms | p99 delta ms | Envoy failure % |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 1 | 141211.42 | 48747.48 | 34.52 | N/A | N/A | N/A | 0.00 |
| 1000 | 1 | 116263.49 | 46852.12 | 40.30 | N/A | N/A | N/A | 0.00 |
| 2000 | 1 | 81154.46 | 41260.74 | 50.84 | N/A | N/A | N/A | 0.00 |
| 3000 | 1 | 76846.98 | 40574.03 | 52.80 | N/A | N/A | N/A | 0.91 |
| 4000 | 1 | 71069.50 | 44600.76 | 62.76 | N/A | N/A | N/A | 25.45 |

## Median across repetitions

| Concurrency | Direct RPS median | Envoy RPS median | RPS ratio median % | Direct p99 median ms | Envoy p99 median ms |
|---:|---:|---:|---:|---:|---:|
| 500 | 141211.42 | 48747.48 | 34.52 | N/A | N/A |
| 1000 | 116263.49 | 46852.12 | 40.30 | N/A | N/A |
| 2000 | 81154.46 | 41260.74 | 50.84 | N/A | N/A |
| 3000 | 76846.98 | 40574.03 | 52.80 | N/A | N/A |
| 4000 | 71069.50 | 44600.76 | 62.76 | N/A | N/A |

## Resource data files

- `pod-resources.csv`: peak and average CPU/memory per Pod per case. CPU in millicores.
- `docker-node-resources.csv`: Docker kind node container CPU%, memory and sampled network I/O.
- `cpu-throttling.csv`: per-node cgroup throttled CPU time and count between case start/end.
- `cases/<case>/resources.jsonl`: raw timestamped host, Docker and Kubernetes samples.
- `snapshot/`: initial Kubernetes and Docker resource/configuration state.

## Interpretation / known limitations

- CPU throttling seconds are **summed across kind node cgroups**, not a single wall-clock stall; do not interpret directly as user-facing latency.
- `docker stats` CPU% is per logical CPU: 100% ≈ one CPU core. Node quotas require a separate comparison with Docker inspect.
- `kubectl top` samples are not an exact total CPU consumption measurement; unavailable metrics are N/A, never zero.
- Prometheus enrichment is optional via scripts/prom_enrich.py; missing data stays N/A. Queries use 1m rate windows.
- `hey` uses a concurrency-driven workload; this is **not** a controlled open-loop fixed-QPS test.
- Same-host kind benchmarking shares physical host CPU and I/O. For production capacity, use external load generator, pin workloads and repeat.
- Review `STOP_REASON.txt` if present; failed cases must not be used to claim sustainable peak capacity.
