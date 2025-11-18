#!/bin/bash

# macOS Trading Bot Manager
# Usage: ./bot-macos.sh [start|stop|restart|status]

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
BACKEND_PID="$SCRIPT_DIR/.backend.pid"
FRONTEND_PID="$SCRIPT_DIR/.frontend.pid"

# Check if process is running
is_running() {
    local pid_file=$1
    [ -f "$pid_file" ] && ps -p $(cat "$pid_file") > /dev/null 2>&1
}

# Start backend
start_backend() {
    if is_running "$BACKEND_PID"; then
        echo -e "${YELLOW}Backend already running (PID: $(cat $BACKEND_PID))${NC}"
        return
    fi

    echo -e "${BLUE}Starting backend...${NC}"
    cd "$BACKEND_DIR"
    nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload > "$SCRIPT_DIR/backend.log" 2>&1 &
    echo $! > "$BACKEND_PID"
    cd "$SCRIPT_DIR"
    sleep 2
    echo -e "${GREEN}✅ Backend started (PID: $(cat $BACKEND_PID))${NC}"
}

# Start frontend
start_frontend() {
    if is_running "$FRONTEND_PID"; then
        echo -e "${YELLOW}Frontend already running (PID: $(cat $FRONTEND_PID))${NC}"
        return
    fi

    echo -e "${BLUE}Starting frontend...${NC}"
    cd "$FRONTEND_DIR"
    nohup npm run dev > "$SCRIPT_DIR/frontend.log" 2>&1 &
    echo $! > "$FRONTEND_PID"
    cd "$SCRIPT_DIR"
    sleep 2
    echo -e "${GREEN}✅ Frontend started (PID: $(cat $FRONTEND_PID))${NC}"
}

# Stop backend
stop_backend() {
    if is_running "$BACKEND_PID"; then
        echo -e "${BLUE}Stopping backend...${NC}"
        kill $(cat "$BACKEND_PID")
        rm -f "$BACKEND_PID"
        echo -e "${GREEN}✅ Backend stopped${NC}"
    else
        echo -e "${YELLOW}Backend not running${NC}"
    fi
}

# Stop frontend
stop_frontend() {
    if is_running "$FRONTEND_PID"; then
        echo -e "${BLUE}Stopping frontend...${NC}"
        kill $(cat "$FRONTEND_PID")
        rm -f "$FRONTEND_PID"
        echo -e "${GREEN}✅ Frontend stopped${NC}"
    else
        echo -e "${YELLOW}Frontend not running${NC}"
    fi
}

# Show status
show_status() {
    echo -e "${BLUE}=== Trading Bot Status ===${NC}"
    echo ""
    echo -n "Backend:  "
    if is_running "$BACKEND_PID"; then
        echo -e "${GREEN}RUNNING${NC} (PID: $(cat $BACKEND_PID))"
        echo "          http://localhost:8100"
    else
        echo -e "${RED}STOPPED${NC}"
    fi

    echo -n "Frontend: "
    if is_running "$FRONTEND_PID"; then
        echo -e "${GREEN}RUNNING${NC} (PID: $(cat $FRONTEND_PID))"
        echo "          http://localhost:5173"
    else
        echo -e "${RED}STOPPED${NC}"
    fi
}

# Main
case "${1:-}" in
    start)
        start_backend
        start_frontend
        ;;
    stop)
        stop_frontend
        stop_backend
        ;;
    restart)
        stop_frontend
        stop_backend
        sleep 2
        start_backend
        start_frontend
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
