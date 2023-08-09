#!/bin/sh
export PATH="$PWD:$PATH"
export PYTHONPATH="${PWD%/*}"
if [ $# = 0 ]; then
    export PYTHONSTARTUP="$PWD/STARTUP"
    cd "$PWD/tests"
    ipython --no-banner --no-confirm-exit
else
    "$@"
fi
