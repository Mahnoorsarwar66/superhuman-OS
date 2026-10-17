#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 || $# != 1 ]]; then echo 'As root: bash rollback_server.sh /home/superhuman/app/backups/v1.39-EXACT_BACKUP' >&2; exit 1; fi
upgrade_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
app_dir=/home/superhuman/app
systemctl stop superhuman-worker.service superhuman-web.service
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" "$3" --rollback "$4"' sh "$app_dir" "$app_dir/.venv/bin/python" "$upgrade_dir/install_v139.py" "$1"
systemctl start superhuman-web.service
echo 'Web restored to v1.38. Worker remains stopped and paused; review queued discussions before resuming.'
