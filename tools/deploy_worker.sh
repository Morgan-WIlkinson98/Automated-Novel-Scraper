#!/usr/bin/env bash
# deploy_worker.sh — build + deploy the `novels-worker` Cloud Run Job.
#
# No gcloud required: the script talks to the GCP REST API with an access
# token minted from a service-account key (python3 + google-auth, both
# already used by this repo) and pushes the image with plain docker.
#
# One-time setup (console.cloud.google.com, project mw-novels —
# ALREADY on the Blaze plan, billing account 016C4E-045E5A-AED2E2):
#   1. Grant the poller service account (the FIREBASE_SERVICE_ACCOUNT_JSON
#      one) these roles on the project:
#        - Cloud Run Developer        (roles/run.developer)
#        - Artifact Registry Writer   (roles/artifactregistry.writer)
#        - Service Usage Consumer     (roles/serviceusage.serviceUsageConsumer)
#        - Cloud Run Invoker          (roles/run.invoker) — for the site's
#                                     jobs:run trigger (NOVELS_SA_JSON)
#      It already needs datastore.user for Firestore — unchanged.
#      Free-tier guardrails: executions are hard-capped monthly by the
#      Firestore ledger (WORKER_MAX_MONTHLY_RUNS, default 20 — worst
#      case ~144k vCPU-s vs the 180k allowance), and a spend cap budget
#      can hard-pause the run.googleapis.com service in the console.
#
# Required env:
#   FIREBASE_SERVICE_ACCOUNT_JSON  — SA key JSON (or path to the file);
#                                    also injected into the job itself
#   NU_COOKIES                     — NU session cookies JSON (optional but
#                                    strongly recommended for extnu resolves)
# Optional env:
#   GCP_PROJECT (default mw-novels) · GCP_REGION (default us-central1)
#   WORKER_JOB (default novels-worker) · WORKER_SA_JSON (deploy identity
#   override — defaults to FIREBASE_SERVICE_ACCOUNT_JSON)
#
# Usage: bash tools/deploy_worker.sh

set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${GCP_PROJECT:-mw-novels}"
REGION="${GCP_REGION:-us-central1}"
JOB="${WORKER_JOB:-novels-worker}"
REPO="novels"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/worker:latest"
SA="${WORKER_SA_JSON:-${FIREBASE_SERVICE_ACCOUNT_JSON:-}}"

if [ -z "$SA" ]; then
    echo "FIREBASE_SERVICE_ACCOUNT_JSON (or WORKER_SA_JSON) is required" >&2
    exit 1
fi
if [ -f "$SA" ]; then SA="$(cat "$SA")"; fi

token() {
    SA_JSON="$SA" python3 - <<'PY'
import json, os
from google.oauth2 import service_account
import google.auth.transport.requests
creds = service_account.Credentials.from_service_account_info(
    json.loads(os.environ["SA_JSON"]),
    scopes=["https://www.googleapis.com/auth/cloud-platform"])
creds.refresh(google.auth.transport.requests.Request())
print(creds.token)
PY
}

api() {  # api METHOD URL [body]
    local method="$1" url="$2" body="${3:-}"
    curl -sf -X "$method" \
        -H "Authorization: Bearer $(token)" \
        -H "Content-Type: application/json" \
        ${body:+-d "$body"} "$url"
}

echo "== Enabling APIs (run, artifactregistry, cloudresourcemanager) =="
api POST "https://serviceusage.googleapis.com/v1/projects/${PROJECT}/services:batchEnable" \
    '{"serviceIds":["run.googleapis.com","artifactregistry.googleapis.com","cloudresourcemanager.googleapis.com"]}' \
    > /dev/null || echo "  (API enable needs the console if roles are missing — continuing)"

echo "== Creating Artifact Registry repo '${REPO}' (skips if present) =="
api POST "https://artifactregistry.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/repositories?repositoryId=${REPO}" \
    '{"format":"DOCKER"}' > /dev/null 2>&1 || true

echo "== docker login + build (linux/amd64 — takes a while under emulation) =="
echo "$SA" | docker login -u _json_key --password-stdin \
    "https://${REGION}-docker.pkg.dev" > /dev/null
docker buildx build --platform linux/amd64 -t "$IMAGE" --push .

echo "== Creating/updating Cloud Run Job '${JOB}' =="
JOB_BODY="$(SA_ENV="$SA" NU_COOKIES="${NU_COOKIES:-}" python3 - "$IMAGE" <<'PY'
import json, os, sys
envs = [
    {"name": "DB_TYPE", "value": "firestore"},
    {"name": "NU_HEADED", "value": "1"},
    {"name": "FIREBASE_SERVICE_ACCOUNT_JSON", "value": os.environ["SA_ENV"]},
]
if os.environ.get("NU_COOKIES"):
    envs.append({"name": "NOVELUPDATES_COOKIES", "value": os.environ["NU_COOKIES"]})
sa = json.loads(os.environ["SA_ENV"])
print(json.dumps({
    "template": {"template": {
        "containers": [{
            "image": sys.argv[1],
            "command": ["xvfb-run", "-a", "python", "queue_worker.py"],
            "env": envs,
            "resources": {"limits": {"memory": "2Gi", "cpu": "2"}},
        }],
        "timeout": "3600s",
        "maxRetries": 0,
        "serviceAccount": sa["client_email"],
    }},
}))
PY
)"

api PUT "https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${JOB}" \
    "$JOB_BODY" > /dev/null

echo
echo "Done. Trigger a full-queue run:"
echo "  curl -X POST -H \"Authorization: Bearer \$(token)\" \\"
echo "    https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${JOB}:run"
echo "Or let the site button do it — it calls this endpoint per request."
