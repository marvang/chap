#!/bin/bash
# Simple overnight launcher - prevents system from sleeping while running experiments
# Works on macOS (caffeinate) and Linux (systemd-inhibit)
# Usage: ./ctf-experiment-runner/run_overnight.sh

cd "$(dirname "$0")/.."

echo "🌙 Starting overnight experiments..."

if [[ "$(uname)" == "Darwin" ]]; then
    echo "   macOS detected: using caffeinate to prevent sleep."
    echo ""
    caffeinate -dims python ctf-experiment-runner/run_overnight.py
else
    if ! command -v systemd-inhibit &> /dev/null; then
        echo "❌ Error: systemd-inhibit not found."
        echo "   Install systemd or run experiments manually with:"
        echo "   python ctf-experiment-runner/run_overnight.py"
        exit 1
    fi
    echo "   Linux detected: using systemd-inhibit to prevent sleep."
    echo ""
    systemd-inhibit --what=sleep:idle python ctf-experiment-runner/run_overnight.py
fi
