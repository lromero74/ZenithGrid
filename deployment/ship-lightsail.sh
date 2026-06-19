#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VERSION="${1:-}"
MODE="${2:---backend}"
SSH_TARGET="${SSH_TARGET:-zenithgrid-ls}"

[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)*$ ]] || {
    echo "usage: $0 VERSION [--backend|--frontend-only]" >&2
    exit 1
}
[ "$MODE" = "--backend" ] || [ "$MODE" = "--frontend-only" ] || {
    echo "invalid mode: $MODE" >&2
    exit 1
}

[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ] || {
    echo "working tree must be clean before shipping" >&2
    exit 1
}
[ "$(git -C "$REPO_ROOT" describe --tags --exact-match 2>/dev/null)" = "$VERSION" ] || {
    echo "HEAD must be tagged $VERSION before shipping" >&2
    exit 1
}

BUILD_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/zenithgrid-${VERSION}.XXXXXX")
trap 'rm -rf "$BUILD_ROOT"' EXIT

echo "Building $VERSION frontend artifact locally..."
(cd "$REPO_ROOT/frontend" && npm run build -- --outDir "$BUILD_ROOT/frontend" --emptyOutDir)
[ -f "$BUILD_ROOT/frontend/index.html" ]
[ -d "$BUILD_ROOT/frontend/assets" ]

echo "Uploading immutable frontend artifact..."
ssh "$SSH_TARGET" "mkdir -p ~/ZenithGrid/frontend/releases/$VERSION"
rsync -az --delete "$BUILD_ROOT/frontend/" \
    "$SSH_TARGET:ZenithGrid/frontend/releases/$VERSION/"

echo "Updating production checkout and atomically activating frontend..."
ssh "$SSH_TARGET" "cd ~/ZenithGrid && \
git fetch origin --tags && git pull --ff-only origin main && \
bash deployment/activate-frontend-release.sh '$VERSION'"

if [ "$MODE" = "--backend" ]; then
    ssh "$SSH_TARGET" 'if systemctl is-enabled --quiet zenithgrid-web.service && \
        systemctl is-enabled --quiet zenithgrid-trader.service; then
        sudo systemctl restart zenithgrid-trader.service
        sudo systemctl restart zenithgrid-web.service
    else
        sudo systemctl restart zenithgrid.service
    fi'
fi

echo "Verifying production..."
ssh "$SSH_TARGET" 'if systemctl is-enabled --quiet zenithgrid-web.service && \
    systemctl is-enabled --quiet zenithgrid-trader.service; then
    expected_services="zenithgrid-web.service zenithgrid-trader.service"
    health_urls="http://127.0.0.1:8100/api/health|web http://127.0.0.1:8101/api/health|trader"
else
    expected_services="zenithgrid.service"
    health_urls="http://127.0.0.1:8100/api/health|combined"
fi
for attempt in {1..12}; do
    healthy=true
    output=""
    for health_target in $health_urls; do
        url=${health_target%|*}
        role=${health_target#*|}
        response=$(curl -fsS "$url") || { healthy=false; break; }
        echo "$response" | grep -q "\"process_role\":\"$role\"" || { healthy=false; break; }
        output="$output$response\n"
    done
    if [ "$healthy" = true ]; then
        printf "%b" "$output"
        exit 0
    fi
    sleep 5
done
echo "ZenithGrid did not become healthy within 60 seconds" >&2
for service in $expected_services; do
    journalctl -u "$service" --no-pager -n 40 >&2
done
exit 1'
echo
echo "Deployed $VERSION ($MODE)"
