#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then echo 'Run on the Ubuntu server as root.' >&2; exit 1; fi
upgrade_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
app_dir=/home/superhuman/app
app_python="$app_dir/.venv/bin/python"
installer="$upgrade_dir/install_v137.py"
for name in superhuman-web.service superhuman-worker.service; do
 if [[ $(systemctl show "$name" --property=User --value) != superhuman ]]; then echo "Unexpected service account for $name; stopped before changes." >&2; exit 1; fi
done
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" "$3" --preflight' sh "$app_dir" "$app_python" "$installer"
restart_services() { systemctl start superhuman-web.service superhuman-worker.service || true; }
trap restart_services EXIT
systemctl stop superhuman-worker.service superhuman-web.service
backup_dir=/home/superhuman/private-backups
install -d -m 700 -o superhuman -g superhuman "$backup_dir"
backup_file="$backup_dir/pre-v137-$(date -u +%Y%m%dT%H%M%S%NZ).zip"
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" -m superhuman.hosted.cli bundle --output "$3"' sh "$app_dir" "$app_python" "$backup_file"
echo "Private data backup: $backup_file"
runuser -u superhuman -- sh -c 'cd "$1" && exec "$2" "$3"' sh "$app_dir" "$app_python" "$installer"
systemctl start superhuman-web.service superhuman-worker.service
systemctl is-active superhuman-web.service superhuman-worker.service
trap - EXIT
echo 'v1.37 installed. Open Settings > Budget to review configuration before any paid test. No authority or budget has been enabled automatically.'
