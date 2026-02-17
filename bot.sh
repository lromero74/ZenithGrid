#!/bin/bash

# ZenithGrid Trading Bot Manager
# Usage: ./bot.sh [start|stop|restart --dev|--prod [--force]|status|logs]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Detect OS
OS_TYPE=$(uname -s)

# Directories and files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
BACKEND_PID_FILE="$SCRIPT_DIR/.backend.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"
BACKEND_LOG="$SCRIPT_DIR/backend.log"
FRONTEND_LOG="$SCRIPT_DIR/frontend.log"

# Service names (for systemd)
BACKEND_SERVICE="trading-bot-backend"
FRONTEND_SERVICE="trading-bot-frontend"

# Ports
BACKEND_PORT=8100
FRONTEND_PORT=5173

# Graceful shutdown timeout (seconds)
SHUTDOWN_TIMEOUT=60

# ── Nginx discovery ─────────────────────────────────────────────────

# Find the nginx config file for this application by searching standard
# nginx directories for a config that proxies to our backend port.
# Returns the path on stdout; returns 1 if not found.
find_nginx_conf() {
    local search_dirs="/etc/nginx/conf.d /etc/nginx/sites-enabled"
    search_dirs="$search_dirs /etc/nginx/sites-available"
    for dir in $search_dirs; do
        [ -d "$dir" ] || continue
        local found
        found=$(grep -rl \
            "proxy_pass http://127.0.0.1:${BACKEND_PORT}" \
            "$dir" 2>/dev/null | head -1)
        if [ -n "$found" ]; then
            echo "$found"
            return 0
        fi
    done
    return 1
}

# Resolve and cache the nginx config path for this session.
# Prints the path on stdout; prints an error and returns 1 if not found.
NGINX_CONF=""
resolve_nginx_conf() {
    if [ -z "$NGINX_CONF" ]; then
        NGINX_CONF=$(find_nginx_conf) || true
    fi
    if [ -z "$NGINX_CONF" ]; then
        echo -e "${RED}Could not find nginx config for this app${NC}" >&2
        echo -e "${YELLOW}  Searched: /etc/nginx/conf.d," \
            "sites-enabled, sites-available${NC}" >&2
        echo -e "${YELLOW}  Looking for proxy_pass to" \
            "port ${BACKEND_PORT}${NC}" >&2
        return 1
    fi
    echo "$NGINX_CONF"
}

# ── Mode detection and switching ────────────────────────────────────

# Detect current deployment mode from nginx config (source of truth).
# Prints "dev", "prod", or "unknown".
get_current_mode() {
    local conf
    conf=$(resolve_nginx_conf 2>/dev/null) || {
        echo "unknown"
        return
    }
    # Check what the main "location / {" block proxies to
    local main_proxy
    main_proxy=$(grep -A3 'location / {' "$conf" \
        | grep proxy_pass | head -1 \
        | grep -o '[0-9]*;' | tr -d ';')
    if [ "$main_proxy" = "$FRONTEND_PORT" ]; then
        echo "dev"
    elif [ "$main_proxy" = "$BACKEND_PORT" ]; then
        echo "prod"
    else
        echo "unknown"
    fi
}

# Check if nginx mode and service state are consistent.
# Returns 0 if consistent, 1 if mixed. Prints warnings on mismatch.
check_mode_consistency() {
    local nginx_mode
    nginx_mode=$(get_current_mode)
    local frontend_running=false
    if is_service_running "$FRONTEND_SERVICE"; then
        frontend_running=true
    fi

    local mixed=false

    if [ "$nginx_mode" = "dev" ] \
        && [ "$frontend_running" = false ]; then
        echo -e "${RED}Mixed mode detected:${NC}"
        echo -e "  Nginx is in DEV mode" \
            "(routing to Vite on ${FRONTEND_PORT})"
        echo -e "  But frontend service is" \
            "${RED}NOT RUNNING${NC}"
        echo -e "  Traffic will fail — nothing" \
            "listening on ${FRONTEND_PORT}"
        mixed=true
    fi

    if [ "$nginx_mode" = "prod" ] \
        && [ "$frontend_running" = true ]; then
        echo -e "${YELLOW}Mixed mode detected:${NC}"
        echo -e "  Nginx is in PROD mode" \
            "(routing to backend on ${BACKEND_PORT})"
        echo -e "  But frontend service is" \
            "${YELLOW}still running${NC}" \
            "(wasting resources)"
        mixed=true
    fi

    if [ "$mixed" = true ]; then
        echo ""
        echo -e "Choose a mode and restart with --force:"
        echo -e "  $0 restart --dev --force" \
            "  # Fix to dev mode"
        echo -e "  $0 restart --prod --force" \
            " # Fix to prod mode"
        return 1
    fi

    return 0
}

# Set the proxy_pass port for the first location block (location /)
set_nginx_main_proxy() {
    local port=$1
    local conf
    conf=$(resolve_nginx_conf) || return 1
    sudo sed -i \
        "0,/proxy_pass http:\/\/127.0.0.1:[0-9]*;/s|\
proxy_pass http://127.0.0.1:[0-9]*;|\
proxy_pass http://127.0.0.1:${port};|" "$conf"
}

# Ensure the /ws location block always points to the backend port
ensure_nginx_ws_backend() {
    local conf
    conf=$(resolve_nginx_conf) || return 1
    sudo sed -i '/location \/ws {/,/}/ s|proxy_pass \
http://127.0.0.1:[0-9]*;|proxy_pass \
http://127.0.0.1:'"${BACKEND_PORT}"';|' "$conf"
}

# Validate nginx config and reload the service
reload_nginx() {
    if sudo nginx -t 2>&1; then
        sudo systemctl reload nginx
        return 0
    else
        echo -e "${RED}Nginx config test failed!${NC}"
        return 1
    fi
}

# Switch to DEV mode: nginx location / → Vite, frontend service enabled
switch_to_dev() {
    echo -e "${BLUE}Switching to DEV mode...${NC}"
    local changed=false

    # 1. Nginx: location / → FRONTEND_PORT (Vite dev server)
    local current_mode
    current_mode=$(get_current_mode)
    if [ "$current_mode" != "dev" ]; then
        echo -e "  Nginx: location / → ${FRONTEND_PORT}" \
            "(Vite dev server)"
        set_nginx_main_proxy "$FRONTEND_PORT"
        ensure_nginx_ws_backend
        changed=true
    else
        echo -e "  Nginx: already pointing to ${FRONTEND_PORT}"
    fi

    # 2. Frontend service: enable + start
    if ! is_service_running "$FRONTEND_SERVICE"; then
        echo -e "  Frontend service: starting..."
        sudo systemctl enable "$FRONTEND_SERVICE" 2>/dev/null \
            || true
        sudo systemctl start "$FRONTEND_SERVICE"
        sleep 2
        if is_service_running "$FRONTEND_SERVICE"; then
            echo -e "  ${GREEN}Frontend service: running${NC}"
        else
            echo -e "  ${RED}Frontend service: failed to start${NC}"
            return 1
        fi
    else
        echo -e "  Frontend service: already running"
    fi

    # 3. Reload nginx if config changed
    if [ "$changed" = true ]; then
        echo -e "  Reloading nginx..."
        reload_nginx || return 1
    fi

    echo -e "${GREEN}DEV mode active${NC}"
    echo -e "  Nginx (443) → Vite (${FRONTEND_PORT})" \
        "→ proxies /api to backend (${BACKEND_PORT})"
    echo -e "  Nginx (443) → Backend (${BACKEND_PORT}) for /ws"
    echo -e "  HMR enabled — frontend changes apply instantly"
}

# Switch to PROD mode: build dist, nginx → backend, frontend disabled
switch_to_prod() {
    echo -e "${BLUE}Switching to PROD mode...${NC}"
    local changed=false

    # 1. Build frontend
    echo -e "  Building frontend..."
    (cd "$FRONTEND_DIR" && npm run build) || {
        echo -e "${RED}Frontend build failed${NC}"
        return 1
    }
    if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
        echo -e "${RED}Build produced no dist/index.html${NC}"
        return 1
    fi
    echo -e "  ${GREEN}Frontend built → dist/${NC}"

    # 2. Stop + disable frontend service
    if is_service_running "$FRONTEND_SERVICE"; then
        echo -e "  Frontend service: stopping..."
        sudo systemctl stop "$FRONTEND_SERVICE"
    fi
    sudo systemctl disable "$FRONTEND_SERVICE" 2>/dev/null || true
    echo -e "  Frontend service: disabled"

    # 3. Nginx: location / → BACKEND_PORT (backend serves dist/)
    local current_mode
    current_mode=$(get_current_mode)
    if [ "$current_mode" != "prod" ]; then
        echo -e "  Nginx: location / → ${BACKEND_PORT}" \
            "(backend serves dist/)"
        set_nginx_main_proxy "$BACKEND_PORT"
        ensure_nginx_ws_backend
        changed=true
    else
        echo -e "  Nginx: already pointing to ${BACKEND_PORT}"
    fi

    # 4. Reload nginx if config changed
    if [ "$changed" = true ]; then
        echo -e "  Reloading nginx..."
        reload_nginx || return 1
    fi

    echo -e "${GREEN}PROD mode active${NC}"
    echo -e "  Nginx (443) → Backend (${BACKEND_PORT})" \
        "→ serves API + dist/ + WebSocket"
    echo -e "  Frontend service: disabled"
    echo -e "  No HMR — frontend changes require rebuild + restart"
}

# ── Service helper functions ────────────────────────────────────────

# Prepare for graceful shutdown (waits for in-flight orders)
prepare_graceful_shutdown() {
    echo -e "${BLUE}Preparing graceful shutdown" \
        "(waiting for in-flight orders)...${NC}"

    local result
    result=$(curl -s -X POST \
        "http://localhost:$BACKEND_PORT/api/system/\
prepare-shutdown?timeout=$SHUTDOWN_TIMEOUT" 2>/dev/null) || {
        echo -e "${YELLOW}Backend not responding" \
            "- proceeding with stop${NC}"
        return 0
    }

    local ready
    ready=$(echo "$result" | grep -o '"ready": *true' || true)
    local in_flight
    in_flight=$(echo "$result" \
        | grep -o '"in_flight_count": *[0-9]*' \
        | grep -o '[0-9]*' || echo "0")
    local message
    message=$(echo "$result" \
        | grep -o '"message": *"[^"]*"' \
        | sed 's/"message": *"\([^"]*\)"/\1/' || true)

    if [ -n "$ready" ]; then
        echo -e "${GREEN}$message${NC}"
    else
        echo -e "${YELLOW}Shutdown timeout:" \
            "$in_flight orders still in-flight${NC}"
        echo -e "${YELLOW}  Proceeding anyway" \
            "(orders will be reconciled on restart)${NC}"
    fi

    return 0
}

# Check if a process is running by PID file (macOS)
is_process_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$pid_file"
            return 1
        fi
    fi
    return 1
}

# Check if a systemd service is running (Linux)
is_service_running() {
    local service=$1
    systemctl is-active --quiet "$service" 2>/dev/null
    return $?
}

# Clear Python bytecode cache
clear_python_cache() {
    echo -e "${BLUE}Clearing Python bytecode cache...${NC}"
    find "$BACKEND_DIR" -type d -name __pycache__ \
        -exec rm -rf {} + 2>/dev/null || true
    find "$BACKEND_DIR" -type f -name "*.pyc" \
        -delete 2>/dev/null || true
    echo -e "${GREEN}Python cache cleared${NC}"
}

# ── Service start/stop functions ────────────────────────────────────

start_backend() {
    echo -e "${BLUE}Starting backend...${NC}"

    clear_python_cache

    if [ "$OS_TYPE" = "Darwin" ]; then
        # macOS - use process management
        if is_process_running "$BACKEND_PID_FILE"; then
            echo -e "${YELLOW}Backend is already running" \
                "(PID: $(cat "$BACKEND_PID_FILE"))${NC}"
            return 0
        fi

        cd "$BACKEND_DIR"
        nohup ./venv/bin/python -m uvicorn app.main:app \
            --host 0.0.0.0 --port $BACKEND_PORT --reload \
            > "$BACKEND_LOG" 2>&1 &
        local backend_pid=$!
        echo $backend_pid > "$BACKEND_PID_FILE"
        cd "$SCRIPT_DIR"
        sleep 3

        if is_process_running "$BACKEND_PID_FILE"; then
            echo -e "${GREEN}Backend started (PID: $backend_pid)${NC}"
            echo -e "${GREEN}  API: http://localhost:$BACKEND_PORT${NC}"
            echo -e "${GREEN}  Logs: tail -f $BACKEND_LOG${NC}"
            return 0
        else
            echo -e "${RED}Backend failed to start${NC}"
            echo -e "${YELLOW}Check logs:" \
                "tail -n 50 $BACKEND_LOG${NC}"
            return 1
        fi
    else
        # Linux - use systemd
        if is_service_running "$BACKEND_SERVICE"; then
            echo -e "${YELLOW}Backend is already running${NC}"
            return 0
        fi

        sudo systemctl start "$BACKEND_SERVICE"
        sleep 2

        if is_service_running "$BACKEND_SERVICE"; then
            echo -e "${GREEN}Backend started${NC}"
            echo -e "${GREEN}  API:" \
                "http://localhost:${BACKEND_PORT}${NC}"
            echo -e "${GREEN}  Logs:" \
                "sudo journalctl -u $BACKEND_SERVICE -f${NC}"
            return 0
        else
            echo -e "${RED}Backend failed to start${NC}"
            echo -e "${YELLOW}Check logs:" \
                "sudo journalctl -u $BACKEND_SERVICE -n 50${NC}"
            return 1
        fi
    fi
}

start_frontend() {
    local mode
    mode=$(get_current_mode)
    if [ "$mode" = "prod" ]; then
        echo -e "${GREEN}Frontend served by backend" \
            "(production build)${NC}"
        echo -e "${GREEN}  URL:" \
            "http://localhost:$BACKEND_PORT${NC}"
        return 0
    fi

    echo -e "${BLUE}Starting frontend (dev mode)...${NC}"

    if is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${YELLOW}Frontend is already running${NC}"
        return 0
    fi

    sudo systemctl start "$FRONTEND_SERVICE"
    sleep 2

    if is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${GREEN}Frontend started (dev mode)${NC}"
        echo -e "${GREEN}  URL:" \
            "http://localhost:${FRONTEND_PORT}${NC}"
        echo -e "${GREEN}  Logs:" \
            "sudo journalctl -u $FRONTEND_SERVICE -f${NC}"
        return 0
    else
        echo -e "${RED}Frontend failed to start${NC}"
        echo -e "${YELLOW}Check logs:" \
            "sudo journalctl -u $FRONTEND_SERVICE -n 50${NC}"
        return 1
    fi
}

stop_backend() {
    echo -e "${BLUE}Stopping backend...${NC}"

    if ! is_service_running "$BACKEND_SERVICE"; then
        echo -e "${YELLOW}Backend is not running${NC}"
        return 0
    fi

    # Graceful shutdown - wait for in-flight orders to complete
    prepare_graceful_shutdown

    sudo systemctl stop "$BACKEND_SERVICE"
    sleep 1

    if ! is_service_running "$BACKEND_SERVICE"; then
        echo -e "${GREEN}Backend stopped${NC}"
    else
        echo -e "${RED}Failed to stop backend${NC}"
        return 1
    fi
}

stop_frontend() {
    local mode
    mode=$(get_current_mode)
    if [ "$mode" = "prod" ]; then
        echo -e "${YELLOW}Frontend served by backend" \
            "(no separate service to stop)${NC}"
        return 0
    fi

    echo -e "${BLUE}Stopping frontend...${NC}"

    if ! is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${YELLOW}Frontend is not running${NC}"
        return 0
    fi

    sudo systemctl stop "$FRONTEND_SERVICE"
    sleep 1

    if ! is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${GREEN}Frontend stopped${NC}"
    else
        echo -e "${RED}Failed to stop frontend${NC}"
        return 1
    fi
}

# ── Display functions ───────────────────────────────────────────────

show_status() {
    echo -e "${BLUE}=== Trading Bot Status ===${NC}"
    echo ""

    local mode
    mode=$(get_current_mode)
    echo -e "Mode:     ${GREEN}${mode^^}${NC}"
    echo ""

    # Backend status
    echo -n "Backend:  "
    if is_service_running "$BACKEND_SERVICE"; then
        echo -e "${GREEN}RUNNING${NC}"
        echo "          http://localhost:${BACKEND_PORT}"
    else
        echo -e "${RED}STOPPED${NC}"
    fi

    # Frontend status
    echo -n "Frontend: "
    if [ "$mode" = "prod" ]; then
        echo -e "${GREEN}PRODUCTION (served by backend)${NC}"
        echo "          http://localhost:$BACKEND_PORT"
    elif is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${GREEN}RUNNING (dev mode)${NC}"
        echo "          http://localhost:${FRONTEND_PORT}"
    else
        echo -e "${RED}STOPPED${NC}"
    fi

    # Nginx config location
    local conf
    conf=$(resolve_nginx_conf 2>/dev/null) || conf="(not found)"
    echo ""
    echo -e "Nginx:    $conf"

    # Check for mixed mode
    echo ""
    check_mode_consistency 2>/dev/null || true

    echo ""
    echo -e "${BLUE}Detailed status:${NC}"
    echo ""
    sudo systemctl status "$BACKEND_SERVICE" --no-pager -l || true
    if [ "$mode" != "prod" ]; then
        echo ""
        sudo systemctl status "$FRONTEND_SERVICE" \
            --no-pager -l || true
    fi
}

show_logs() {
    echo -e "${BLUE}=== Recent Logs ===${NC}"
    echo ""

    echo -e "${YELLOW}Backend (last 20 lines):${NC}"
    sudo journalctl -u "$BACKEND_SERVICE" -n 20 --no-pager
    echo ""

    local mode
    mode=$(get_current_mode)
    if [ "$mode" != "prod" ]; then
        echo -e "${YELLOW}Frontend (last 20 lines):${NC}"
        sudo journalctl -u "$FRONTEND_SERVICE" -n 20 --no-pager
        echo ""
    fi

    echo -e "${BLUE}To follow logs in real-time:${NC}"
    echo "  Backend:  sudo journalctl -u $BACKEND_SERVICE -f"
    if [ "$mode" != "prod" ]; then
        echo "  Frontend: sudo journalctl -u $FRONTEND_SERVICE -f"
    fi
}

# ── Main script logic ──────────────────────────────────────────────

case "${1:-}" in
    start)
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}  Starting Trading Bot${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""

        start_backend
        backend_ok=$?

        echo ""

        start_frontend
        frontend_ok=$?

        echo ""
        echo -e "${GREEN}========================================${NC}"

        if [ $backend_ok -eq 0 ] && [ $frontend_ok -eq 0 ]; then
            echo -e "${GREEN}Trading Bot started successfully!${NC}"
            echo ""
            local_mode=$(get_current_mode)
            echo -e "${YELLOW}Next steps:${NC}"
            if [ "$local_mode" = "prod" ]; then
                echo "  1. Open http://localhost:$BACKEND_PORT"
            else
                echo "  1. Open http://localhost:${FRONTEND_PORT}"
            fi
            echo "  2. Add your Coinbase API credentials" \
                "in Settings"
            echo "  3. Click 'Start Bot' to begin monitoring"
            echo ""
            echo "  View logs:    ./bot.sh logs"
            echo "  Check status: ./bot.sh status"
            echo "  Stop bot:     ./bot.sh stop"
        else
            echo -e "${RED}Some services failed to start${NC}"
            echo -e "${YELLOW}Check logs: ./bot.sh logs${NC}"
        fi
        echo -e "${GREEN}========================================${NC}"
        ;;

    stop)
        echo -e "${RED}========================================${NC}"
        echo -e "${RED}  Stopping Trading Bot${NC}"
        echo -e "${RED}========================================${NC}"
        echo ""

        stop_frontend
        echo ""
        stop_backend

        echo ""
        echo -e "${RED}========================================${NC}"
        echo -e "${GREEN}Trading Bot stopped${NC}"
        echo -e "${RED}========================================${NC}"
        ;;

    restart)
        # Require --dev or --prod flag
        MODE_FLAG="${2:-}"
        FORCE_FLAG="${3:-}"
        if [ "$MODE_FLAG" != "--dev" ] \
            && [ "$MODE_FLAG" != "--prod" ]; then
            echo -e "${RED}restart requires" \
                "--dev or --prod flag${NC}"
            echo ""
            echo "Usage:"
            echo "  $0 restart --dev   " \
                "# Restart in dev mode (Vite HMR)"
            echo "  $0 restart --prod  " \
                "# Restart in prod mode (built dist/)"
            echo ""
            echo "Current mode: $(get_current_mode)"
            exit 1
        fi

        TARGET_MODE="${MODE_FLAG#--}"
        CURRENT_MODE=$(get_current_mode)

        # Guard: warn if switching deployment modes
        if [ "$CURRENT_MODE" != "unknown" ] \
            && [ "$CURRENT_MODE" != "$TARGET_MODE" ]; then
            if [ "$FORCE_FLAG" != "--force" ]; then
                echo -e "${YELLOW}========================================${NC}"
                echo -e "${YELLOW}  Mode change detected${NC}"
                echo -e "${YELLOW}========================================${NC}"
                echo ""
                echo -e "Currently running in" \
                    "${GREEN}${CURRENT_MODE^^}${NC} mode."
                echo -e "Did you mean to switch to" \
                    "${BLUE}${TARGET_MODE^^}${NC} deployment?"
                echo ""
                echo -e "If yes, re-run with --force:"
                echo -e "  $0 restart ${MODE_FLAG} --force"
                echo ""
                exit 1
            fi
            echo -e "${YELLOW}Switching from" \
                "${CURRENT_MODE^^} → ${TARGET_MODE^^}" \
                "(--force)${NC}"
            echo ""
        fi

        # Guard: warn if infrastructure is in a mixed state
        if [ "$FORCE_FLAG" != "--force" ]; then
            if ! check_mode_consistency; then
                exit 1
            fi
        fi

        echo -e "${YELLOW}========================================${NC}"
        echo -e "${YELLOW}  Restarting Trading Bot" \
            "(${TARGET_MODE} mode)${NC}"
        echo -e "${YELLOW}========================================${NC}"
        echo ""

        # Clear bytecode cache before restarting
        clear_python_cache
        echo ""

        # Graceful shutdown - wait for in-flight orders
        if is_service_running "$BACKEND_SERVICE"; then
            prepare_graceful_shutdown
        fi
        echo ""

        # Switch mode (handles nginx config + frontend service)
        if [ "$TARGET_MODE" = "dev" ]; then
            switch_to_dev
        else
            switch_to_prod
        fi
        echo ""

        # Restart backend
        echo -e "${BLUE}Restarting backend...${NC}"
        sudo systemctl restart "$BACKEND_SERVICE"
        sleep 2
        if is_service_running "$BACKEND_SERVICE"; then
            echo -e "${GREEN}Backend restarted${NC}"
        else
            echo -e "${RED}Backend failed to restart${NC}"
            echo -e "${YELLOW}Check logs:" \
                "sudo journalctl -u $BACKEND_SERVICE -n 50${NC}"
        fi

        # In dev mode, also restart the frontend service
        if [ "$TARGET_MODE" = "dev" ]; then
            echo ""
            echo -e "${BLUE}Restarting frontend...${NC}"
            sudo systemctl restart "$FRONTEND_SERVICE"
            sleep 2
            if is_service_running "$FRONTEND_SERVICE"; then
                echo -e "${GREEN}Frontend restarted${NC}"
            else
                echo -e "${RED}Frontend failed to restart${NC}"
                echo -e "${YELLOW}Check logs:" \
                    "sudo journalctl -u $FRONTEND_SERVICE" \
                    "-n 50${NC}"
            fi
        fi

        echo ""
        echo -e "${YELLOW}========================================${NC}"
        echo -e "${GREEN}Trading Bot restarted" \
            "(${TARGET_MODE} mode)${NC}"
        echo -e "${YELLOW}========================================${NC}"
        ;;

    status)
        show_status
        ;;

    logs)
        show_logs
        ;;

    *)
        echo -e "${BLUE}ZenithGrid Trading Bot Manager${NC}"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  start              Start backend and frontend"
        echo "  stop               Gracefully stop all services"
        echo "  restart --dev      Restart in dev mode" \
            "(Vite HMR, nginx → ${FRONTEND_PORT})"
        echo "  restart --prod     Restart in prod mode" \
            "(build dist/, nginx → ${BACKEND_PORT})"
        echo "  status             Show mode, services, and nginx"
        echo "  logs               Show recent logs"
        echo ""
        echo "Modes:"
        echo "  --dev   Nginx routes to Vite dev server" \
            "(port ${FRONTEND_PORT}) for HMR."
        echo "          Frontend service runs alongside" \
            "backend."
        echo "  --prod  Builds frontend to dist/. Nginx" \
            "routes to backend (port ${BACKEND_PORT})."
        echo "          Backend serves static files." \
            "Frontend service disabled."
        echo ""
        echo "  --force is required when switching between" \
            "modes (e.g., dev → prod)."
        echo "  Without --force, the script warns and" \
            "exits to prevent accidental mode changes."
        echo ""
        echo "Examples:"
        echo "  $0 start                  # Start services"
        echo "  $0 restart --dev          # Restart in dev mode"
        echo "  $0 restart --prod         # Restart in prod mode"
        echo "  $0 restart --prod --force # Switch dev → prod"
        echo "  $0 status                 # Check mode and services"
        echo "  $0 stop                   # Gracefully stop the bot"
        echo ""
        exit 1
        ;;
esac
