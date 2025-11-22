#!/bin/bash

# ETH/BTC Trading Bot - Cross-Platform Manager
# Usage: ./bot.sh [start|stop|restart|status|logs]

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

# Function to check if process is running (macOS/Linux)
is_process_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$pid_file"
            return 1
        fi
    fi
    return 1
}

# Function to check if systemd service is running (Linux)
is_service_running() {
    local service=$1
    systemctl is-active --quiet "$service" 2>/dev/null
    return $?
}

# Function to clear Python bytecode cache
clear_python_cache() {
    echo -e "${BLUE}Clearing Python bytecode cache...${NC}"
    find "$BACKEND_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find "$BACKEND_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
    echo -e "${GREEN}✅ Python cache cleared${NC}"
}

# Function to start backend
start_backend() {
    echo -e "${BLUE}Starting backend...${NC}"

    # Clear bytecode cache before starting
    clear_python_cache

    if [ "$OS_TYPE" = "Darwin" ]; then
        # macOS - use process management
        if is_process_running "$BACKEND_PID_FILE"; then
            echo -e "${YELLOW}Backend is already running (PID: $(cat $BACKEND_PID_FILE))${NC}"
            return 0
        fi

        cd "$BACKEND_DIR"
        nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload > "$BACKEND_LOG" 2>&1 &
        local backend_pid=$!
        echo $backend_pid > "$BACKEND_PID_FILE"
        cd "$SCRIPT_DIR"
        sleep 3

        if is_process_running "$BACKEND_PID_FILE"; then
            echo -e "${GREEN}✅ Backend started (PID: $backend_pid)${NC}"
            echo -e "${GREEN}   API: http://localhost:$BACKEND_PORT${NC}"
            echo -e "${GREEN}   Logs: tail -f $BACKEND_LOG${NC}"
            return 0
        else
            echo -e "${RED}❌ Backend failed to start${NC}"
            echo -e "${YELLOW}Check logs: tail -n 50 $BACKEND_LOG${NC}"
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
            echo -e "${GREEN}✅ Backend started${NC}"
            echo -e "${GREEN}   API: http://localhost:8100${NC}"
            echo -e "${GREEN}   Logs: sudo journalctl -u $BACKEND_SERVICE -f${NC}"
            return 0
        else
            echo -e "${RED}❌ Backend failed to start${NC}"
            echo -e "${YELLOW}Check logs: sudo journalctl -u $BACKEND_SERVICE -n 50${NC}"
            return 1
        fi
    fi
}

# Function to start frontend
start_frontend() {
    echo -e "${BLUE}Starting frontend...${NC}"

    if is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${YELLOW}Frontend is already running${NC}"
        return 0
    fi

    sudo systemctl start "$FRONTEND_SERVICE"
    sleep 2

    if is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${GREEN}✅ Frontend started${NC}"
        echo -e "${GREEN}   URL: http://localhost:5173${NC}"
        echo -e "${GREEN}   Logs: sudo journalctl -u $FRONTEND_SERVICE -f${NC}"
        return 0
    else
        echo -e "${RED}❌ Frontend failed to start${NC}"
        echo -e "${YELLOW}Check logs: sudo journalctl -u $FRONTEND_SERVICE -n 50${NC}"
        return 1
    fi
}

# Function to stop backend
stop_backend() {
    echo -e "${BLUE}Stopping backend...${NC}"

    if ! is_service_running "$BACKEND_SERVICE"; then
        echo -e "${YELLOW}Backend is not running${NC}"
        return 0
    fi

    sudo systemctl stop "$BACKEND_SERVICE"
    sleep 1

    if ! is_service_running "$BACKEND_SERVICE"; then
        echo -e "${GREEN}✅ Backend stopped${NC}"
    else
        echo -e "${RED}❌ Failed to stop backend${NC}"
        return 1
    fi
}

# Function to stop frontend
stop_frontend() {
    echo -e "${BLUE}Stopping frontend...${NC}"

    if ! is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${YELLOW}Frontend is not running${NC}"
        return 0
    fi

    sudo systemctl stop "$FRONTEND_SERVICE"
    sleep 1

    if ! is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${GREEN}✅ Frontend stopped${NC}"
    else
        echo -e "${RED}❌ Failed to stop frontend${NC}"
        return 1
    fi
}

# Function to show status
show_status() {
    echo -e "${BLUE}=== Trading Bot Status ===${NC}"
    echo ""

    # Backend status
    echo -n "Backend:  "
    if is_service_running "$BACKEND_SERVICE"; then
        echo -e "${GREEN}RUNNING${NC}"
        echo "          http://localhost:8000"
    else
        echo -e "${RED}STOPPED${NC}"
    fi

    # Frontend status
    echo -n "Frontend: "
    if is_service_running "$FRONTEND_SERVICE"; then
        echo -e "${GREEN}RUNNING${NC}"
        echo "          http://localhost:5173"
    else
        echo -e "${RED}STOPPED${NC}"
    fi

    echo ""
    echo -e "${BLUE}Detailed status:${NC}"
    echo ""
    sudo systemctl status "$BACKEND_SERVICE" --no-pager -l || true
    echo ""
    sudo systemctl status "$FRONTEND_SERVICE" --no-pager -l || true
}

# Function to show logs
show_logs() {
    echo -e "${BLUE}=== Recent Logs ===${NC}"
    echo ""

    echo -e "${YELLOW}Backend (last 20 lines):${NC}"
    sudo journalctl -u "$BACKEND_SERVICE" -n 20 --no-pager
    echo ""

    echo -e "${YELLOW}Frontend (last 20 lines):${NC}"
    sudo journalctl -u "$FRONTEND_SERVICE" -n 20 --no-pager
    echo ""

    echo -e "${BLUE}To follow logs in real-time:${NC}"
    echo "  Backend:  sudo journalctl -u $BACKEND_SERVICE -f"
    echo "  Frontend: sudo journalctl -u $FRONTEND_SERVICE -f"
}

# Main script logic
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
            echo -e "${GREEN}✅ Trading Bot started successfully!${NC}"
            echo ""
            echo -e "${YELLOW}Next steps:${NC}"
            echo "  1. Open http://localhost:5173 in your browser"
            echo "  2. Add your Coinbase API credentials in Settings"
            echo "  3. Click 'Start Bot' to begin monitoring"
            echo ""
            echo "  View logs:   ./bot.sh logs"
            echo "  Check status: ./bot.sh status"
            echo "  Stop bot:    ./bot.sh stop"
        else
            echo -e "${RED}⚠️  Some services failed to start${NC}"
            echo -e "${YELLOW}Check logs with: ./bot.sh logs${NC}"
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
        echo -e "${GREEN}✅ Trading Bot stopped${NC}"
        echo -e "${RED}========================================${NC}"
        ;;

    restart)
        echo -e "${YELLOW}========================================${NC}"
        echo -e "${YELLOW}  Restarting Trading Bot${NC}"
        echo -e "${YELLOW}========================================${NC}"
        echo ""

        # Clear bytecode cache before restarting
        clear_python_cache
        echo ""

        echo -e "${BLUE}Restarting backend...${NC}"
        sudo systemctl restart "$BACKEND_SERVICE"
        sleep 2
        echo -e "${GREEN}✅ Backend restarted${NC}"

        echo ""
        echo -e "${BLUE}Restarting frontend...${NC}"
        sudo systemctl restart "$FRONTEND_SERVICE"
        sleep 2
        echo -e "${GREEN}✅ Frontend restarted${NC}"

        echo ""
        echo -e "${YELLOW}========================================${NC}"
        echo -e "${GREEN}✅ Trading Bot restarted${NC}"
        echo -e "${YELLOW}========================================${NC}"
        ;;

    status)
        show_status
        ;;

    logs)
        show_logs
        ;;

    *)
        echo -e "${BLUE}ETH/BTC Trading Bot - Local Development Manager${NC}"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  start    - Start backend and frontend"
        echo "  stop     - Stop backend and frontend"
        echo "  restart  - Restart backend and frontend"
        echo "  status   - Show running status"
        echo "  logs     - Show recent logs"
        echo ""
        echo "Examples:"
        echo "  $0 start    # Start the bot"
        echo "  $0 status   # Check if running"
        echo "  $0 logs     # View recent logs"
        echo "  $0 restart  # Restart everything"
        echo "  $0 stop     # Stop the bot"
        echo ""
        exit 1
        ;;
esac
