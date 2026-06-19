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
    ssh "$SSH_TARGET" "sudo systemctl restart zenithgrid"
fi

echo "Verifying production..."
ssh "$SSH_TARGET" 'systemctl is-active zenithgrid >/dev/null || exit 1
for attempt in {1..12}; do
    if curl -fsS http://127.0.0.1:8100/api/health; then
        exit 0
    fi
    sleep 5
done
echo "ZenithGrid did not become healthy within 60 seconds" >&2
journalctl -u zenithgrid --no-pager -n 40 >&2
exit 1'
echo
echo "Deployed $VERSION ($MODE)"
