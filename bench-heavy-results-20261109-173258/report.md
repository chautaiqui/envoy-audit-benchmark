# Envoy Gateway — High Load Benchmark Report

Source: `/root/envoy-audit-benchmark/bench-heavy-results-20261109-173258`

**Important:** these are measurements on the kind VM, not independently verified production capacity. Direct and Envoy paths differ in network hops.

## Run-level results

| Case | RPS | p50 ms | p95 ms | p99 ms | HTTP 200 | Non-200 | Transport errors | Failure % | Host CPU peak % | Envoy CPU avg sum (m) | Throttling s (sum, nodes) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| direct-c100-r1 | 160972.41 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 38.58 | 1478.07 | 0.00 |
| direct-c1000-r1 | 97857.92 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 44.23 | 1632.47 | 0.00 |
| direct-c2000-r1 | 92734.23 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 43.30 | 1834.29 | 0.00 |
| direct-c500-r1 | 144442.92 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 39.98 | 2013.50 | 0.00 |
| envoy-c100-r1 | 48268.91 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 32.47 | 2366.31 | 4.86 |
| envoy-c1000-r1 | 46420.51 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 37.28 | 2424.86 | 0.00 |
| envoy-c2000-r1 | 42791.63 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 34.85 | 2013.85 | 0.00 |
| envoy-c500-r1 | 50344.56 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 38.62 | 2442.12 | 0.00 |

## Paired Direct vs Envoy

| Concurrency | Repeat | Direct RPS | Envoy RPS | Envoy / Direct % | Direct p99 ms | Envoy p99 ms | p99 delta ms | Envoy failure % |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 1 | 160972.41 | 48268.91 | 29.99 | N/A | N/A | N/A | 0.00 |
| 500 | 1 | 144442.92 | 50344.56 | 34.85 | N/A | N/A | N/A | 0.00 |
| 1000 | 1 | 97857.92 | 46420.51 | 47.44 | N/A | N/A | N/A | 0.00 |
| 2000 | 1 | 92734.23 | 42791.63 | 46.14 | N/A | N/A | N/A | 0.00 |

## Median across repetitions

| Concurrency | Direct RPS median | Envoy RPS median | RPS ratio median % | Direct p99 median ms | Envoy p99 median ms |
|---:|---:|---:|---:|---:|---:|
| 100 | 160972.41 | 48268.91 | 29.99 | N/A | N/A |
| 500 | 144442.92 | 50344.56 | 34.85 | N/A | N/A |
| 1000 | 97857.92 | 46420.51 | 47.44 | N/A | N/A |
| 2000 | 92734.23 | 42791.63 | 46.14 | N/A | N/A |

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
