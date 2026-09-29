#!/usr/bin/env bash
# Runs the pipeline inside the project's virtualenv: ./edupipe.sh <command> ...
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/.venv/bin/python" -m edupipe "$@"
