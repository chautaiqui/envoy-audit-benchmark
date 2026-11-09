# Envoy Gateway — High Load Benchmark Report

Source: `/root/envoy-audit-benchmark/bench-heavy-results-20261109-175628`

**Important:** these are measurements on the kind VM, not independently verified production capacity. Direct and Envoy paths differ in network hops.

## Run-level results

| Case | RPS | p50 ms | p95 ms | p99 ms | HTTP 200 | Non-200 | Transport errors | Failure % | Host CPU peak % | Envoy CPU avg sum (m) | Throttling s (sum, nodes) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| direct-c2000-r1 | 93671.65 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 43.76 | 1568.91 | 1.39 |
| direct-c4000-r1 | 77734.62 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 46.02 | 2022.27 | 0.00 |
| envoy-c2000-r1 | 44089.56 | N/A | N/A | N/A | 883649 | 0 | 0 | 0.00 | 36.99 | 2290.82 | 0.00 |
| envoy-c4000-r1 | 45447.16 | N/A | N/A | N/A | 668973 | 244418 | 0 | 26.76 | 37.44 | 1626.67 | 4.13 |

## Paired Direct vs Envoy

| Concurrency | Repeat | Direct RPS | Envoy RPS | Envoy / Direct % | Direct p99 ms | Envoy p99 ms | p99 delta ms | Envoy failure % |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2000 | 1 | 93671.65 | 44089.56 | 47.07 | N/A | N/A | N/A | 0.00 |
| 4000 | 1 | 77734.62 | 45447.16 | 58.46 | N/A | N/A | N/A | 26.76 |

## Median across repetitions

| Concurrency | Direct RPS median | Envoy RPS median | RPS ratio median % | Direct p99 median ms | Envoy p99 median ms |
|---:|---:|---:|---:|---:|---:|
| 2000 | 93671.65 | 44089.56 | 47.07 | N/A | N/A |
| 4000 | 77734.62 | 45447.16 | 58.46 | N/A | N/A |

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
