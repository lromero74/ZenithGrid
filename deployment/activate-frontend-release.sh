#!/usr/bin/env bash
set -euo pipefail

FRONTEND_ROOT="${FRONTEND_ROOT:-$HOME/ZenithGrid/frontend}"
RELEASES_DIR="$FRONTEND_ROOT/releases"
DIST_LINK="$FRONTEND_ROOT/dist"
PREVIOUS_FILE="$FRONTEND_ROOT/.previous-frontend-release"
NGINX_FRONTEND_ROOT="${NGINX_FRONTEND_ROOT:-/var/www/zenithgrid/current}"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

atomic_replace_link() {
    python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$1" "$2"
}

publish_nginx_frontend_root() {
    local release_dir="$1"
    sudo mkdir -p "$NGINX_FRONTEND_ROOT"
    sudo rsync -a --delete "$release_dir/" "$NGINX_FRONTEND_ROOT/"
    sudo chown -R root:root "$NGINX_FRONTEND_ROOT"
    sudo find "$NGINX_FRONTEND_ROOT" -type d -exec chmod 755 {} +
    sudo find "$NGINX_FRONTEND_ROOT" -type f -exec chmod 644 {} +
}

activate_release() {
    local release_name="$1"
    [[ "$release_name" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)*$ ]] \
        || fail "invalid release name: $release_name"

    local release_dir="$RELEASES_DIR/$release_name"
    [ -f "$release_dir/index.html" ] || fail "$release_name has no index.html"
    [ -d "$release_dir/assets" ] || fail "$release_name has no assets directory"

    mkdir -p "$RELEASES_DIR"
    local current_target=""
    if [ -L "$DIST_LINK" ]; then
        current_target=$(readlink "$DIST_LINK")
    elif [ -d "$DIST_LINK" ]; then
        local legacy_name="legacy-$(date -u +%Y%m%d%H%M%S)"
        mv "$DIST_LINK" "$RELEASES_DIR/$legacy_name"
        current_target="releases/$legacy_name"
    elif [ -e "$DIST_LINK" ]; then
        fail "$DIST_LINK exists but is not a directory or symlink"
    fi

    if [ -n "$current_target" ] && [ "$current_target" != "releases/$release_name" ]; then
        printf '%s\n' "$current_target" > "$PREVIOUS_FILE"
    fi

    rm -f "$DIST_LINK.next"
    ln -s "releases/$release_name" "$DIST_LINK.next"
    atomic_replace_link "$DIST_LINK.next" "$DIST_LINK"
    publish_nginx_frontend_root "$release_dir"
    echo "Activated frontend $release_name"
}

rollback_release() {
    [ -f "$PREVIOUS_FILE" ] || fail "no previous frontend release is recorded"
    local previous_target
    previous_target=$(cat "$PREVIOUS_FILE")
    [ -f "$FRONTEND_ROOT/$previous_target/index.html" ] \
        || fail "recorded previous release is unavailable: $previous_target"

    local current_target=""
    [ -L "$DIST_LINK" ] && current_target=$(readlink "$DIST_LINK")
    rm -f "$DIST_LINK.next"
    ln -s "$previous_target" "$DIST_LINK.next"
    atomic_replace_link "$DIST_LINK.next" "$DIST_LINK"
    publish_nginx_frontend_root "$FRONTEND_ROOT/$previous_target"
    [ -n "$current_target" ] && printf '%s\n' "$current_target" > "$PREVIOUS_FILE"
    echo "Rolled frontend back to $previous_target"
}

case "${1:-}" in
    --rollback)
        rollback_release
        ;;
    "")
        fail "usage: $0 VERSION | --rollback"
        ;;
    *)
        activate_release "$1"
        ;;
esac
