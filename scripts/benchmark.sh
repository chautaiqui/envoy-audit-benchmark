#!/usr/bin/env bash
set -euo pipefail
command -v hey >/dev/null || { echo 'Missing hey in PATH'; exit 1; }
command -v kubectl >/dev/null || exit 1
NODE_IP="${NODE_IP:-172.18.0.7}"  # Must be an Envoy-local node if externalTrafficPolicy=Local
HOST="${HOST:-httpbin.dev.local}"
NS=platform-test
PUBLIC_SVC="$(kubectl get svc -n envoy-gateway-system -l gateway.envoyproxy.io/owning-gateway-name=public-gateway -o jsonpath='{.items[0].metadata.name}')"
GATEWAY_PORT="$(kubectl get svc "$PUBLIC_SVC" -n envoy-gateway-system -o jsonpath='{.spec.ports[?(@.port==80)].nodePort}')"
DIRECT_PORT="$(kubectl get svc bench-direct -n "$NS" -o jsonpath='{.spec.ports[0].nodePort}')"
[[ -n "$GATEWAY_PORT" && -n "$DIRECT_PORT" ]] || { echo 'Missing NodePort'; exit 1; }
GATEWAY="http://${NODE_IP}:${GATEWAY_PORT}/bench"
DIRECT="http://${NODE_IP}:${DIRECT_PORT}/bench"
OUT="${OUT:-$(pwd)/bench-results-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
printf 'node=%s\ngateway=%s\ndirect=%s\n' "$NODE_IP" "$GATEWAY" "$DIRECT" | tee "$OUT/metadata.txt"
smoke(){
  local uri="$1"; shift
  local status
  status="$(env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 10 "$@" "$uri")"
  echo "$uri => $status"
  [[ "$status" == 200 ]]
}
smoke "$DIRECT"
smoke "$GATEWAY" -H "Host: $HOST"
run(){
  local name="$1" concurrency="$2" seconds="$3" uri="$4" hostflag="$5"
  echo "RUN $name c=$concurrency seconds=$seconds" | tee -a "$OUT/run.log"
  local -a args=(-z "${seconds}s" -c "$concurrency")
  if [[ "$hostflag" == yes ]]; then args+=(-host "$HOST"); fi
  ( env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy hey "${args[@]}" "$uri" ) | tee "$OUT/${name}-c${concurrency}.txt"
  sleep 10
}
run direct-warmup 50 20 "$DIRECT" no
run envoy-warmup 50 20 "$GATEWAY" yes
for c in 100 250 500 1000; do
  run direct "$c" 45 "$DIRECT" no
  run envoy "$c" 45 "$GATEWAY" yes
done
cat <<TXT
Results: $OUT
Review Requests/sec, latency p50/p95/p99, non-200 status, host CPU and Envoy Pod metrics.
Do NOT infer gateway CPU overhead solely by comparing two NodePort paths.
TXT
