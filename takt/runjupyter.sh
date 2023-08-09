#!/bin/sh
export PATH="$PWD:$PATH"
export PYTHONPATH="${PWD%/*}"
export PYTHONSTARTUP="$PWD/STARTUP"
jupyter-notebook stop
sleep 1
jupyter-notebook 2>/dev/null &
