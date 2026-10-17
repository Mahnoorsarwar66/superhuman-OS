#!/usr/bin/env bash
# Restore only this upgrade's code. User data is retained.
set -euo pipefail
if [[ $(id -u) != 0 ]]; then echo 'Run on Ubuntu as root.' >&2; exit 1; fi
if [[ $# != 1 ]]; then echo 'Usage: bash rollback_server.sh /home/superhuman/app/backups/v1.31-TIMESTAMP' >&2; exit 1; fi
upgrade_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
app_dir=/home/superhuman/app
restart_services() { systemctl start superhuman-web.service superhuman-worker.service || true; }
trap restart_services EXIT
systemctl stop superhuman-worker.service superhuman-web.service
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" -c "from superhuman.hosted.jobs import pause; pause(True)"' sh "$app_dir" "$app_dir/.venv/bin/python"
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" "$3" --rollback "$4"' sh "$app_dir" "$app_dir/.venv/bin/python" "$upgrade_dir/install_v131.py" "$1"
systemctl start superhuman-web.service superhuman-worker.service
systemctl is-active superhuman-web.service superhuman-worker.service
trap - EXIT
