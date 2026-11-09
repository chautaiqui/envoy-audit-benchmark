# Envoy Gateway — High Load Benchmark Report

Source: `/root/envoy-audit-benchmark/bench-heavy-results-20261109-164617`

**Important:** these are measurements on the kind VM, not independently verified production capacity. Direct and Envoy paths differ in network hops.

## Run-level results

| Case | RPS | p50 ms | p95 ms | p99 ms | HTTP 200 | Non-200 | Transport errors | Failure % | Host CPU peak % | Envoy CPU avg sum (m) | Throttling s (sum, nodes) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| direct-c100-r1 | 148077.73 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 38.92 | N/A | 0.00 |
| direct-c250-r1 | 136564.89 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 40.50 | N/A | 0.00 |
| direct-c500-r1 | 133976.29 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 40.65 | N/A | 1.03 |
| envoy-c100-r1 | 49450.99 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 33.53 | N/A | 0.00 |
| envoy-c250-r1 | 51514.99 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 37.03 | N/A | 0.00 |
| envoy-c500-r1 | 50521.66 | N/A | N/A | N/A | 1000000 | 0 | 0 | 0.00 | 37.79 | N/A | 0.00 |

## Paired Direct vs Envoy

| Concurrency | Repeat | Direct RPS | Envoy RPS | Envoy / Direct % | Direct p99 ms | Envoy p99 ms | p99 delta ms | Envoy failure % |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 1 | 148077.73 | 49450.99 | 33.40 | N/A | N/A | N/A | 0.00 |
| 250 | 1 | 136564.89 | 51514.99 | 37.72 | N/A | N/A | N/A | 0.00 |
| 500 | 1 | 133976.29 | 50521.66 | 37.71 | N/A | N/A | N/A | 0.00 |

## Median across repetitions

| Concurrency | Direct RPS median | Envoy RPS median | RPS ratio median % | Direct p99 median ms | Envoy p99 median ms |
|---:|---:|---:|---:|---:|---:|
| 100 | 148077.73 | 49450.99 | 33.40 | N/A | N/A |
| 250 | 136564.89 | 51514.99 | 37.72 | N/A | N/A |
| 500 | 133976.29 | 50521.66 | 37.71 | N/A | N/A |

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
- Prometheus metrics, request bytes/second and TCP connection stats are not automatically available from this benchmark; compare with Grafana separately.
- `hey` uses a concurrency-driven workload; this is **not** a controlled open-loop fixed-QPS test.
- Same-host kind benchmarking shares physical host CPU and I/O. For production capacity, use external load generator, pin workloads and repeat.
- Review `STOP_REASON.txt` if present; failed cases must not be used to claim sustainable peak capacity.
