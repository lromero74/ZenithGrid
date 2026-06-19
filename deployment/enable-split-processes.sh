#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

[ "${EUID}" -eq 0 ] || {
    echo "run with sudo on the Lightsail production host" >&2
    exit 1
}

wait_for_role() {
    local port=$1
    local role=$2
    for attempt in {1..12}; do
        if curl -fsS "http://127.0.0.1:${port}/api/health" | grep -q "\"process_role\":\"${role}\""; then
            return 0
        fi
        sleep 5
    done
    return 1
}

rollback_to_combined() {
    echo "Restoring combined service" >&2
    systemctl disable --now zenithgrid-web.service zenithgrid-trader.service || true
    systemctl enable --now zenithgrid.service
}

if [ "${1:-}" = "--rollback" ]; then
    rollback_to_combined
    exit 0
fi

trap rollback_to_combined ERR

install -m 0644 "$REPO_ROOT/deployment/zenithgrid-web.service" /etc/systemd/system/zenithgrid-web.service
install -m 0644 "$REPO_ROOT/deployment/zenithgrid-trader.service" /etc/systemd/system/zenithgrid-trader.service
systemctl daemon-reload

systemctl disable --now zenithgrid.service
systemctl enable --now zenithgrid-trader.service
wait_for_role 8101 trader
systemctl enable --now zenithgrid-web.service
wait_for_role 8100 web

trap - ERR
echo "Split processes active: web=:8100, trader=:8101"
