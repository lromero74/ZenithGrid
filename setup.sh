#!/bin/bash
#
# Zenith Grid Setup Wizard Launcher
# ==================================
# This script launches the Python setup wizard.
# It works on both Linux and macOS.
#
# Usage: ./setup.sh
#

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check for Python 3
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version 2>&1 | grep -oP '\d+\.\d+')
    if [[ $(echo "$PYTHON_VERSION >= 3.8" | bc -l) -eq 1 ]]; then
        PYTHON_CMD="python"
    else
        echo "Error: Python 3.8+ is required"
        exit 1
    fi
else
    echo "Error: Python 3 not found. Please install Python 3.8+"
    exit 1
fi

# Run the setup wizard
exec "$PYTHON_CMD" "$SCRIPT_DIR/setup.py" "$@"
