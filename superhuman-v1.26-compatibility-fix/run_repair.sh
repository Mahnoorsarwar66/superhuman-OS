#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then echo 'Run this repair on the Ubuntu server as root.' >&2; exit 1; fi
fix_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
upgrade_dir=/home/superhuman/superhuman-v1.26-upgrade
app_python=/home/superhuman/app/.venv/bin/python
runuser -u superhuman -- "$app_python" "$fix_dir/apply_repair.py" --upgrade-dir "$upgrade_dir"
bash "$upgrade_dir/upgrade_server.sh"
if [[ -f /home/superhuman/superhuman-v1.27-upgrade/upgrade_server.sh ]]; then
    bash /home/superhuman/superhuman-v1.27-upgrade/upgrade_server.sh
else
    echo 'v1.26 installation succeeded. Upload v1.27 and run its upgrade_server.sh when ready.'
fi
