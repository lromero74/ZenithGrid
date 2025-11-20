#!/bin/bash
# Management script for auto-deployment system

case "$1" in
    status)
        echo "Auto-deploy timer status:"
        sudo systemctl status auto-deploy.timer --no-pager
        echo ""
        echo "Recent deployment log:"
        tail -20 ~/auto-deploy.log 2>/dev/null || echo "No deployment log yet"
        ;;
    logs)
        tail -f ~/auto-deploy.log
        ;;
    stop)
        sudo systemctl stop auto-deploy.timer
        echo "Auto-deployment stopped"
        ;;
    start)
        sudo systemctl start auto-deploy.timer
        echo "Auto-deployment started"
        ;;
    restart)
        sudo systemctl restart auto-deploy.timer
        echo "Auto-deployment timer restarted"
        ;;
    *)
        echo "Usage: $0 {status|logs|stop|start|restart}"
        echo ""
        echo "  status  - Show timer status and recent deployments"
        echo "  logs    - Follow deployment log in real-time"
        echo "  stop    - Stop auto-deployment"
        echo "  start   - Start auto-deployment"
        echo "  restart - Restart auto-deployment timer"
        exit 1
        ;;
esac
