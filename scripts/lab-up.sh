#!/usr/bin/env bash
# Bring up the whole lab on Kubernetes: KServe + llm-d + Gateway API, the
# OTel-first observability stack, the model, the API and the frontend.
#
# Two profiles, same manifests:
#
#   PROFILE=local  No GPU. A kind cluster on your laptop; apps/mock-llm stands
#                  in for vLLM behind the real llm-d endpoint picker and Envoy
#                  Gateway. Use it to build dashboards, rehearse recordings and
#                  test routing, SLO and PII rules. Latencies are illustrative.
#   PROFILE=gpu    The GPU node (K3s from scripts/bootstrap.sh, or any cluster
#                  with an NVIDIA GPU). Qwen3.5-9B FP8 on vLLM v0.31.
#
#   ./scripts/lab-up.sh                              # PROFILE=local
#   PROFILE=gpu KUBECONFIG=~/.kube/ocr-lab.config \
#     API_IMAGE=ghcr.io/<you>/ocr-lab-api:0.2.0 \
#     FRONTEND_IMAGE=ghcr.io/<you>/ocr-lab-frontend:0.2.0 ./scripts/lab-up.sh
#
# Needs: kubectl, helm, docker (local: kind). Idempotent; SKIP_PLATFORM=true
# skips the KServe/llm-d install and SKIP_OBSERVABILITY=true the monitoring
# stack on re-runs.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${PROFILE:-local}"
NS="${NS:-default}"
CLUSTER_NAME="${CLUSTER_NAME:-ocr-lab}"
MODEL_NAME="${MODEL_NAME:-qwen3-5-9b}"
GATEWAY_NAME="${GATEWAY_NAME:-kserve-ingress-gateway}"

log() { echo "[lab-up:${PROFILE}] $*"; }
require() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
require kubectl
require helm

case "$PROFILE" in
  local)
    require docker
    require kind
    API_IMAGE="${API_IMAGE:-ocr-lab-api:dev}"
    FRONTEND_IMAGE="${FRONTEND_IMAGE:-ocr-lab-frontend:dev}"
    MOCK_IMAGE="${MOCK_IMAGE:-ocr-lab-mock-llm:dev}"
    if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
      log "Creating kind cluster ${CLUSTER_NAME}..."
      kind create cluster --name "$CLUSTER_NAME" --wait 120s
    fi
    kubectl config use-context "kind-${CLUSTER_NAME}" >/dev/null
    log "Building and loading images (api, frontend, mock-llm)..."
    docker build -q -t "$API_IMAGE" "$REPO_ROOT/apps/api" >/dev/null
    docker build -q -t "$FRONTEND_IMAGE" "$REPO_ROOT/apps/frontend" >/dev/null
    docker build -q -t "$MOCK_IMAGE" "$REPO_ROOT/apps/mock-llm" >/dev/null
    kind load docker-image --name "$CLUSTER_NAME" "$API_IMAGE" "$FRONTEND_IMAGE" "$MOCK_IMAGE"
    MODEL_VALUES=(-f "$REPO_ROOT/charts/model-llmd/values-mock.yaml" --set "mock.image=${MOCK_IMAGE}")
    GPU=false
    ;;
  gpu)
    API_IMAGE="${API_IMAGE:?set API_IMAGE (pushed to a registry the node can pull)}"
    FRONTEND_IMAGE="${FRONTEND_IMAGE:?set FRONTEND_IMAGE}"
    MODEL_VALUES=()
    GPU=true
    ;;
  *) echo "PROFILE must be local or gpu" >&2; exit 1 ;;
esac

kubectl get nodes -o wide

# 1. Platform: KServe v0.21 (LLMInferenceService) + llm-d + Gateway API ------------
if [[ -z "${SKIP_PLATFORM:-}" ]]; then
  if [[ "$PROFILE" == "gpu" ]]; then
    log "1/5 NVIDIA device plugin"
    SKIP_KSERVE=true SKIP_CERT_MANAGER=true "$REPO_ROOT/scripts/install-cluster-deps.sh"
  fi
  log "1/5 KServe + llm-d + Envoy Gateway"
  "$REPO_ROOT/scripts/install-llmisvc.sh"
fi

# 2. Observability: Prometheus (OTLP store), Loki, Tempo, Grafana, OTel Collector --
if [[ -z "${SKIP_OBSERVABILITY:-}" ]]; then
  log "2/5 Observability stack (GPU=${GPU})"
  GPU="$GPU" "$REPO_ROOT/observability/install.sh"
fi

# 3. Model --------------------------------------------------------------------------
log "3/5 Model: LLMInferenceService ${MODEL_NAME} (${PROFILE})"
# The key on the model's route (charts/model-llmd modelAuth), created once and read
# by both the gateway and the API.
if ! kubectl -n "$NS" get secret model-api-key >/dev/null 2>&1; then
  kubectl -n "$NS" create secret generic model-api-key --from-literal=api-key="$(openssl rand -hex 32)"
fi
helm upgrade --install model "$REPO_ROOT/charts/model-llmd" -n "$NS" \
  --set "model.name=${MODEL_NAME}" ${MODEL_VALUES[@]+"${MODEL_VALUES[@]}"}
log "Waiting for ${MODEL_NAME} to be Ready (first GPU start downloads ~14 GB)..."
kubectl -n "$NS" wait "llminferenceservice/${MODEL_NAME}" --for=condition=Ready --timeout="${MODEL_TIMEOUT:-30m}"
# With maxUnavailable: 1 a Deployment counts as Available with zero pods, so Ready
# can be true while the model is still downloading. Wait for the pod itself.
kubectl -n "$NS" rollout status "deployment/${MODEL_NAME}-kserve" --timeout="${MODEL_TIMEOUT:-30m}"

# The API calls the model through the Gateway, inside the cluster: Envoy's own
# Service, then the route KServe created (/<namespace>/<name>/v1/...).
ENVOY_SVC=$(kubectl -n envoy-gateway-system get svc \
  -l "gateway.envoyproxy.io/owning-gateway-name=${GATEWAY_NAME}" -o jsonpath='{.items[0].metadata.name}')
MODEL_URL="http://${ENVOY_SVC}.envoy-gateway-system.svc.cluster.local/${NS}/${MODEL_NAME}"
log "Model route: ${MODEL_URL}"

# 4. API ----------------------------------------------------------------------------
log "4/5 API"
helm upgrade --install ocr-api "$REPO_ROOT/charts/api" -n "$NS" \
  --set image.repository="${API_IMAGE%:*}" --set image.tag="${API_IMAGE##*:}" \
  --set env.OPENAI_BASE_URL="$MODEL_URL" \
  --set env.OPENAI_MODEL_NAME="$MODEL_NAME" \
  --set env.OTEL_RESOURCE_ATTRIBUTES="service.namespace=ocr-lab\,deployment.environment.name=${PROFILE}" \
  --wait --timeout 5m

# 5. Frontend on the same Gateway ---------------------------------------------------
log "5/5 Frontend (HTTPRoute on ${GATEWAY_NAME})"
helm upgrade --install ocr-frontend "$REPO_ROOT/charts/frontend" -n "$NS" \
  --set image.repository="${FRONTEND_IMAGE%:*}" --set image.tag="${FRONTEND_IMAGE##*:}" \
  --set ingress.enabled=false --set httpRoute.enabled=true \
  --wait --timeout 5m

log "Done."
kubectl -n "$NS" get llminferenceservice,pods
cat <<EOF

App:      kubectl -n envoy-gateway-system port-forward svc/${ENVOY_SVC} 8080:80   -> http://localhost:8080
Grafana:  kubectl -n monitoring port-forward svc/kps-grafana 3000:80               -> http://localhost:3000
Load:     k6 run -e BASE_URL=http://localhost:8080/api -e SCENARIO=users loadtest/k6/ocr-users.js
EOF
