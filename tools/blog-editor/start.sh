#!/usr/bin/env bash
# Start the blog editor from any directory.
cd "$(dirname "$0")" && exec python3 serve.py "$@"
