#!/usr/bin/env bash
# Run on Ubuntu as root. No changes to Nginx, authentication, credentials or data.
set -euo pipefail
if [[ $(id -u) != 0 ]]; then echo 'Run this script on the Ubuntu server as root.' >&2; exit 1; fi
upgrade_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
app_dir=/home/superhuman/app
app_python="$app_dir/.venv/bin/python"
installer="$upgrade_dir/install_v134.py"
for name in superhuman-web.service superhuman-worker.service; do
    if [[ $(systemctl show "$name" --property=User --value) != superhuman ]]; then
        echo "Unexpected service account for $name. Stopped before changes." >&2; exit 1
    fi
done
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" "$3" --preflight' sh "$app_dir" "$app_python" "$installer"
restart_services() { systemctl start superhuman-web.service superhuman-worker.service || true; }
trap restart_services EXIT
systemctl stop superhuman-worker.service superhuman-web.service
backup_dir=/home/superhuman/private-backups
install -d -m 700 -o superhuman -g superhuman "$backup_dir"
backup_file="$backup_dir/pre-v134-$(date -u +%Y%m%dT%H%M%S%NZ).zip"
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" -m superhuman.hosted.cli bundle --output "$3"' sh "$app_dir" "$app_python" "$backup_file"
echo "Private data backup: $backup_file"
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" "$3"' sh "$app_dir" "$app_python" "$installer"
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" -m superhuman.practice.cli check' sh "$app_dir" "$app_python"
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" -m superhuman.practice.cli setup' sh "$app_dir" "$app_python"
systemctl start superhuman-web.service superhuman-worker.service
systemctl is-active superhuman-web.service superhuman-worker.service
trap - EXIT
echo 'Installed project interviews and workspace v1.34. Open https://superhuman.167-71-196-20.sslip.io/'
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" -m superhuman.repairs.cli check' sh "$app_dir" "$app_python"
echo 'Open Team to see the employee board and Team Room. Existing channel consent and budgets are preserved.'

echo 'Open Settings > System baseline to review local activation evidence. Configuration is not live connectivity proof.'

runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" -m superhuman.foundation.cli capture' sh "$app_dir" "$app_python"
