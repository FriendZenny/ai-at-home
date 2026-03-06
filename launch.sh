#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/core"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
MAIN="$SCRIPT_DIR/main.py"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Install/update requirements
echo "Checking requirements..."
"$VENV_DIR/bin/pip" install -r "$REQUIREMENTS" --quiet

# Launch
"$VENV_DIR/bin/python" "$MAIN"
