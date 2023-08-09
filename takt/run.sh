#!/bin/sh
export PATH="$PWD:$PATH"
export PYTHONPATH="${PWD%/*}"
if [ $# = 0 ]; then
    export PYTHONSTARTUP="$PWD/STARTUP"
    cd "$PWD/tests"
    python3 -q
else
    "$@"
fi
