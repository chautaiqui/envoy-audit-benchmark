# Envoy Gateway Benchmark Report

Source: `bench-results-20261109-154632` · Generated from actual hey output (no fabricated measurements).

## Results

| Concurrency | Path | RPS | p50 (ms) | p95 (ms) | p99 (ms) | HTTP 200 | Non-200 | Transport errors |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 100 | direct | 163170.71 | N/A | N/A | N/A | 1000000 | 0 | 0 |
| 100 | envoy | 49946.85 | N/A | N/A | N/A | 1000000 | 0 | 0 |
| 250 | direct | 144183.31 | N/A | N/A | N/A | 1000000 | 0 | 0 |
| 250 | envoy | 52682.16 | N/A | N/A | N/A | 1000000 | 0 | 0 |
| 500 | direct | 141876.05 | N/A | N/A | N/A | 1000000 | 0 | 0 |
| 500 | envoy | 51368.03 | N/A | N/A | N/A | 1000000 | 0 | 0 |
| 1000 | direct | 100338.86 | N/A | N/A | N/A | 1000000 | 0 | 0 |
| 1000 | envoy | 48128.01 | N/A | N/A | N/A | 1000000 | 0 | 0 |

## Direct vs Envoy

| Concurrency | Envoy / Direct RPS | p99 delta (ms) | Notes |
|---:|---:|---:|---|
| 100 | 30.61% | N/A | Review load-generator saturation and resource metrics |
| 250 | 36.54% | N/A | Review load-generator saturation and resource metrics |
| 500 | 36.21% | N/A | Review load-generator saturation and resource metrics |
| 1000 | 47.97% | N/A | Review load-generator saturation and resource metrics |

## Interpretation and limitations

- `RPS ratio` = Envoy RPS / Direct RPS × 100%; it is not a pure measurement of Envoy CPU overhead.
- `p99 delta` = Envoy p99 − Direct p99 at the same concurrency. Compare only when response size, error rate and backend conditions match.
- HTTP error counts and transport errors are different. Read the original hey logs if counts are suspicious.
- This script does not collect CPU, RAM, throttling, Prometheus metrics, or configuration state. Collect those independently.
- Both paths use Kubernetes NodePort; on a single-host kind lab the client shares host resources with proxy and backends.
- For capacity conclusions, fix Envoy placement, run at least 3 repetitions per case, ideally use an external load generator and report medians.

## Raw files

- `direct-c100.txt`
- `direct-c1000.txt`
- `direct-c250.txt`
- `direct-c500.txt`
- `direct-warmup-c50.txt`
- `envoy-c100.txt`
- `envoy-c1000.txt`
- `envoy-c250.txt`
- `envoy-c500.txt`
- `envoy-warmup-c50.txt`
- `metadata.txt`
