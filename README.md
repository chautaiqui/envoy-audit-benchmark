# Envoy Gateway 1.9 / kind 6-node audit + benchmark

## 1. Audit

```bash
./scripts/audit.sh
```

Audit is read-only. Validate Gateway conditions, service endpoints, proxy Pod placement, node-group labels, all node NodePorts, metrics availability. When `externalTrafficPolicy=Local`, only nodes with local ready Envoy Pods should be selected for Gateway NodePort tests. **Do not change traffic policy blindly before collecting baseline.**

## 2. Benchmark deployment

The benchmark uses the preloaded `nginx:stable-alpine` image. `bench-api` (4 pods) is exposed through `bench-direct` NodePort and `/bench` via the **existing** `httpbin.dev.local` Public Gateway. The more-specific `/bench` match should win over HTTPBin's `/` route. If the gateway listener excludes that hostname or the HTTPRoute is not Accepted, fix that before testing.

```bash
kubectl apply --dry-run=server -f manifests/bench.yaml
kubectl apply -f manifests/bench.yaml
kubectl rollout status deployment/bench-api -n platform-test --timeout=180s
kubectl get httproute bench-through-envoy -n platform-test -o yaml
kubectl get pods -n platform-test -l app=bench-api -o wide
```

Confirm `Accepted=True`, `ResolvedRefs=True`, ready endpoint slices. If image is missing, `docker pull nginx:stable-alpine` and load the linux/amd64-only archive into kind as previously done.

## 3. Run benchmark

```bash
NODE_IP=172.18.0.7 ./scripts/benchmark.sh
```

`NODE_IP` must be selected based on the current Envoy endpoints when `externalTrafficPolicy=Local`. With `Cluster`, any healthy NodePort node can work, but the network path differs. Do not use port-forward for measurements. The script requires `hey`, runs a warm-up, then alternates direct and gateway at concurrency 100, 250, 500, 1000 for 45 seconds. Modify according to actual saturation and repeat at least 3 times.

For reference, metrics are exposed by the Proxy at `/stats/prometheus` (port 19001) and by the Controller at `/metrics` (port 19001); confirm Prometheus scraping and per-proxy label separation.

## 4. Cleanup

```bash
kubectl delete -f manifests/bench.yaml
```

## Constraints

- These tests run on kind inside a shared VM; benchmark from a separate load-generation VM for capacity-grade conclusions.
- Both test paths traverse kube-proxy NodePort; differences are not pure Envoy CPU overhead.
- Kubernetes Docker cgroup quotas are not dedicated CPUs or isolated machines.
- Do not compare benchmark runs with different proxy replicas, traffic policies, keep-alive settings or backend capacity.
- SLO and high-load stress tests need host/Envoy CPU, throttling, RPS, error rate and p95/p99 reporting.
