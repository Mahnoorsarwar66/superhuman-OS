# Install v1.27 over v1.26

## Before installation

v1.26 must have installed successfully. Its team, USD ledger, model rate cards, projects, memories and accounts are retained; this upgrade does not reset the $200 pilot budget.

If the original v1.26 installer stopped with a missing `gmail_connect.py` error, its isolated checks did not switch the source. Use the corrected v1.26 download, or copy this package's included `gmail_connect.py` into `/home/superhuman/superhuman-v1.26-upgrade/`, rerun the v1.26 installation, then install v1.27. The helper is required by the inherited Gmail setup tests. Do not bypass a failed check or attempt v1.27 directly over v1.25.

## Windows PowerShell

Extract the ZIP to make this path exist:

`C:\superhuman-os-starter\superhuman-v1.27-upgrade\upgrade_server.sh`

Upload and sign in using your replacement SSH key:

```powershell
scp -r -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" "C:\superhuman-os-starter\superhuman-v1.27-upgrade" superhuman@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

## Ubuntu SSH session

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.27-upgrade
bash /home/superhuman/superhuman-v1.27-upgrade/upgrade_server.sh
```

Run the Ubuntu commands after SSH connects. They are not Windows PowerShell commands. Expect a temporary service interruption while the isolated checks run.

The script verifies the known v1.26 source, stops web/worker, saves a private migration backup, tests a staged copy with fake providers, backs up the changed source, installs and restarts both services. It retains existing credentials, keys, origin and settings. A source mismatch or failed test prevents the switch. Keep the error output if the source guard refuses your installation.

The installer prints a source-backup path and a private data-backup path. Retain them privately on the server. A source-only upgrade ZIP does not contain your data or external encryption key.

## Activate gradually

1. Open https://superhuman.167-71-196-20.sslip.io/ and choose **Talk → Personal assistant**.
2. Initialize assistant records. This does not enable reading or paid work.
3. Follow CONNECTION_GUIDE.md. Start with one email inbox or one Slack conversation. WhatsApp Business setup is optional.
4. Under **Connections & consent**, enable reading for that connection. Inspect an actual source preview. Then explicitly allow model analysis if you want these private excerpts sent to the configured Team model.
5. Under **Briefing schedule**, check Asia/Karachi, default 09:00 / 14:00 / 20:30, and daily ceiling 12. Enable the assistant. The Team must be enabled and its dollar budget/rate card valid.
6. Request one fresh briefing, inspect its source links, edit one local reply draft, and confirm that a specialist proposal stays proposed until you approve private sharing. No message should be sent remotely.
7. Check the provider usage dashboard alongside the Twin dollar ledger. Expand channel coverage after the first successful cycle.

The daily ceiling reserves three attempts for scheduled briefs. Manual briefs and intake share the remaining allowance. Failed model attempts count. Idle polling uses no model calls. Pausing the assistant stops analysis; connection reading has its own switch. The worker pause stops polling and analysis; an enabled WhatsApp webhook can still cache signed inbound messages, so disable that channel to stop receipt.

Sensitive Team assignments now exclude public-web tools. Existing private runs that still carry those tools are held. On the Team task page, provide an inspection note and use **Remove public-web tools from private run**. This only restricts tools and does not change required evidence or automatically resume a paused task. If public research was a required tool, prepare a revised private assignment instead of weakening its acceptance criteria.

## Verify

```bash
systemctl is-active superhuman-web.service superhuman-worker.service
cd /home/superhuman/app
runuser -u superhuman -- .venv/bin/python -m superhuman.repairs.cli check
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli status
journalctl -u superhuman-worker.service -n 80 --no-pager
```

The release was tested locally, not on your live host or with your connected accounts. Live checks must confirm actual Slack access, email freshness, signed WhatsApp receipt and the next scheduled briefing.

## Rollback

Use the exact v1.27 source-backup directory printed by installation:

```bash
bash /home/superhuman/superhuman-v1.27-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.27-TIMESTAMP
```

Rollback restores v1.26 source and removes the communications package. Sources, drafts, proposals, schedules, credentials, audit history, Team records and USD accounting remain in the database. It disables communications reading/analysis, cancels queued communications jobs, disables the Team and leaves the global worker paused for inspection. It does not delete or recall anything from a remote account. Reapply v1.27 and explicitly re-enable controls after inspection to continue. Changed source or a damaged/different backup is refused before rollback. Roll back v1.27 before attempting a v1.26 code rollback.
