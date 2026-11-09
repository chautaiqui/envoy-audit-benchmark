#!/usr/bin/env bash
set -uo pipefail
OUT="${OUT:-$(pwd)/audit-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
exec > >(tee "$OUT/summary.log") 2>&1
section(){ printf '\n========== %s ==========\n' "$1"; }
collect(){ local filename="$1"; shift; "$@" > "$OUT/$filename" 2>&1 || true; }
section 'CONTEXT AND VERSIONS'
kubectl config current-context; kubectl version; kind get clusters; helm list -A
collect nodes.txt kubectl get nodes -o wide
collect node-labels.txt kubectl get nodes -L node-group
collect node-describe.txt kubectl describe nodes
collect resources.txt kubectl top nodes
collect pods-all.txt kubectl get pods -A -o wide
collect events.txt kubectl get events -A --sort-by=.metadata.creationTimestamp
cat "$OUT/node-labels.txt"
section 'CORE K8S'
kubectl get ds kube-proxy -n kube-system
kubectl get pods -n kube-system -o wide
section 'GATEWAY'
collect gateways.yaml kubectl get gatewayclass,gateway,httproute -A -o yaml
collect envoyproxy.yaml kubectl get envoyproxy -A -o yaml
collect envoy-service.yaml kubectl get svc -n envoy-gateway-system -o yaml
collect envoy-endpoints.yaml kubectl get endpointslice -n envoy-gateway-system -o yaml
collect routes.txt kubectl get httproute -A
kubectl get gatewayclass; kubectl get gateway -A; kubectl get envoyproxy -A
kubectl get deployments,pods,svc -n envoy-gateway-system -o wide
kubectl get pods -n envoy-gateway-system -l gateway.envoyproxy.io/owning-gateway-name=public-gateway -o wide
section 'BACKEND'
kubectl get deployment,svc,pod,endpointslice -n platform-test -o wide || true
section 'MONITORING'
kubectl get pods,svc -n monitoring -o wide || true
section 'DOCKER QUOTAS'
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' | grep -E 'NAME|envoy-lab-' || true
section 'PUBLIC NODEPORT DISCOVERY'
SVC="$(kubectl get svc -n envoy-gateway-system -l gateway.envoyproxy.io/owning-gateway-name=public-gateway -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "$SVC" ]]; then echo 'FAIL: no public envoy service'; exit 2; fi
POLICY="$(kubectl get svc "$SVC" -n envoy-gateway-system -o jsonpath='{.spec.externalTrafficPolicy}')"
PORT="$(kubectl get svc "$SVC" -n envoy-gateway-system -o jsonpath='{.spec.ports[?(@.port==80)].nodePort}')"
echo "Service=$SVC policy=$POLICY NodePort=$PORT"
if [[ -z "$PORT" ]]; then echo 'FAIL: no HTTP NodePort'; exit 2; fi
section 'ALL NODES HTTP SMOKE TEST'
for node in $(kubectl get nodes -o name | cut -d/ -f2); do
  ip="$(kubectl get node "$node" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')"
  status="$(curl --noproxy '*' --connect-timeout 2 --max-time 5 -sS -o /dev/null -w '%{http_code}' -H 'Host: httpbin.dev.local' "http://${ip}:${PORT}/get" 2>&1)"
  printf '%-26s %-16s %s\n' "$node" "$ip" "$status"
done
section 'READINESS GATES'
echo 'Check READY status, EndpointSlice addresses+conditions, Gateway conditions, Proxy pod placement and HTTP 200 above.'
echo "Audit saved to: $OUT"
