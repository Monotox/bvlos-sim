#!/bin/sh
set -eu

usage() {
    echo "Usage: launch.sh <copter|plane>" >&2
}

case "${1:-}" in
    copter)
        cd /opt/ardupilot
        exec Tools/autotest/sim_vehicle.py -v ArduCopter \
            --no-rebuild --no-mavproxy -I0 --speedup=1
        ;;
    plane)
        cd /opt/ardupilot
        exec Tools/autotest/sim_vehicle.py -v ArduPlane \
            -f quadplane --no-rebuild --no-mavproxy -I1 --speedup=1
        ;;
    *)
        usage
        exit 1
        ;;
esac
