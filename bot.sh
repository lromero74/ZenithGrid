#!/bin/bash

# ETH/BTC Trading Bot - Local Development Manager
# Usage: ./bot.sh [start|stop|restart|status|logs]

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
PID_DIR="$PROJECT_DIR/.pids"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create PID directory
mkdir -p "$PID_DIR"

# Function to check if process is running
is_running() {
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

# Function to start backend
start_backend() {
    echo -e "${BLUE}Starting backend...${NC}"

    # Check if already running
    if is_running "$PID_DIR/backend.pid"; then
        echo -e "${YELLOW}Backend is already running (PID: $(cat $PID_DIR/backend.pid))${NC}"
        return 0
    fi

    # Check if .env exists
    if [ ! -f "$BACKEND_DIR/.env" ]; then
        echo -e "${RED}ERROR: $BACKEND_DIR/.env not found${NC}"
        echo -e "${YELLOW}Please create .env file with your Coinbase credentials${NC}"
        return 1
    fi

    # Check if venv exists
    if [ ! -d "$BACKEND_DIR/venv" ]; then
        echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
        cd "$BACKEND_DIR"
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        deactivate
        cd "$PROJECT_DIR"
    fi

    # Start backend
    cd "$BACKEND_DIR"
    source venv/bin/activate
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$PID_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"
    deactivate
    cd "$PROJECT_DIR"

    sleep 2

    if is_running "$PID_DIR/backend.pid"; then
        echo -e "${GREEN}✅ Backend started (PID: $(cat $PID_DIR/backend.pid))${NC}"
        echo -e "${GREEN}   API: http://localhost:8000${NC}"
        echo -e "${GREEN}   Logs: $PID_DIR/backend.log${NC}"
        return 0
    else
        echo -e "${RED}❌ Backend failed to start${NC}"
        echo -e "${YELLOW}Check logs: tail -f $PID_DIR/backend.log${NC}"
        return 1
    fi
}

# Function to start frontend
start_frontend() {
    echo -e "${BLUE}Starting frontend...${NC}"

    # Check if already running
    if is_running "$PID_DIR/frontend.pid"; then
        echo -e "${YELLOW}Frontend is already running (PID: $(cat $PID_DIR/frontend.pid))${NC}"
        return 0
    fi

    # Kill any process using port 5173
    if lsof -Pi :5173 -sTCP:LISTEN -t > /dev/null 2>&1; then
        echo -e "${YELLOW}Port 5173 is in use. Killing processes...${NC}"
        lsof -ti:5173 | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    # Check if node_modules exists
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        echo -e "${YELLOW}node_modules not found. Installing dependencies...${NC}"
        cd "$FRONTEND_DIR"
        npm install
        cd "$PROJECT_DIR"
    fi

    # Start frontend
    cd "$FRONTEND_DIR"
    nohup npm run dev > "$PID_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"
    cd "$PROJECT_DIR"

    sleep 3

    if is_running "$PID_DIR/frontend.pid"; then
        echo -e "${GREEN}✅ Frontend started (PID: $(cat $PID_DIR/frontend.pid))${NC}"
        echo -e "${GREEN}   URL: http://localhost:5173${NC}"
        echo -e "${GREEN}   Logs: $PID_DIR/frontend.log${NC}"
        return 0
    else
        echo -e "${RED}❌ Frontend failed to start${NC}"
        echo -e "${YELLOW}Check logs: tail -f $PID_DIR/frontend.log${NC}"
        return 1
    fi
}

# Function to stop backend
stop_backend() {
    echo -e "${BLUE}Stopping backend...${NC}"

    if is_running "$PID_DIR/backend.pid"; then
        local pid=$(cat "$PID_DIR/backend.pid")
        kill "$pid" 2>/dev/null || true

        # Wait for graceful shutdown
        for i in {1..10}; do
            if ! ps -p "$pid" > /dev/null 2>&1; then
                break
            fi
            sleep 0.5
        done

        # Force kill if still running
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi

        rm -f "$PID_DIR/backend.pid"
        echo -e "${GREEN}✅ Backend stopped${NC}"
    else
        echo -e "${YELLOW}Backend is not running${NC}"
    fi
}

# Function to stop frontend
stop_frontend() {
    echo -e "${BLUE}Stopping frontend...${NC}"

    if is_running "$PID_DIR/frontend.pid"; then
        local pid=$(cat "$PID_DIR/frontend.pid")

        # Kill the process tree (npm and vite)
        pkill -P "$pid" 2>/dev/null || true
        kill "$pid" 2>/dev/null || true

        # Wait for graceful shutdown
        sleep 1

        # Force kill if still running
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi

        rm -f "$PID_DIR/frontend.pid"
        echo -e "${GREEN}✅ Frontend stopped${NC}"
    else
        echo -e "${YELLOW}Frontend is not running${NC}"
    fi
}

# Function to show status
show_status() {
    echo -e "${BLUE}=== Trading Bot Status ===${NC}"
    echo ""

    # Backend status
    echo -n "Backend:  "
    if is_running "$PID_DIR/backend.pid"; then
        echo -e "${GREEN}RUNNING${NC} (PID: $(cat $PID_DIR/backend.pid))"
        echo "          http://localhost:8000"
    else
        echo -e "${RED}STOPPED${NC}"
    fi

    # Frontend status
    echo -n "Frontend: "
    if is_running "$PID_DIR/frontend.pid"; then
        echo -e "${GREEN}RUNNING${NC} (PID: $(cat $PID_DIR/frontend.pid))"
        echo "          http://localhost:5173"
    else
        echo -e "${RED}STOPPED${NC}"
    fi

    echo ""
}

# Function to show logs
show_logs() {
    echo -e "${BLUE}=== Recent Logs ===${NC}"
    echo ""

    if [ -f "$PID_DIR/backend.log" ]; then
        echo -e "${YELLOW}Backend (last 20 lines):${NC}"
        tail -n 20 "$PID_DIR/backend.log"
        echo ""
    fi

    if [ -f "$PID_DIR/frontend.log" ]; then
        echo -e "${YELLOW}Frontend (last 20 lines):${NC}"
        tail -n 20 "$PID_DIR/frontend.log"
        echo ""
    fi

    echo -e "${BLUE}To follow logs in real-time:${NC}"
    echo "  Backend:  tail -f $PID_DIR/backend.log"
    echo "  Frontend: tail -f $PID_DIR/frontend.log"
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

        stop_frontend
        echo ""
        stop_backend

        echo ""
        echo -e "${BLUE}Waiting 2 seconds...${NC}"
        sleep 2
        echo ""

        start_backend
        echo ""
        start_frontend

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
