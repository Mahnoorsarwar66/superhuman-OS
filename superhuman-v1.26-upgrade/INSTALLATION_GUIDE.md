# Install v1.26 over v1.25

## 1. Download and extract on Windows

Extract superhuman-v1.26-upgrade.zip so this file exists:

`C:\superhuman-os-starter\superhuman-v1.26-upgrade\upgrade_server.sh`

Avoid an extra nested folder. Use the replacement SSH key already configured for this server. Do not upload private keys or your local .venv.

In PowerShell:

```powershell
scp -r -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" "C:\superhuman-os-starter\superhuman-v1.26-upgrade" superhuman@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

## 2. Install on Ubuntu

In that SSH session:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.26-upgrade
bash /home/superhuman/superhuman-v1.26-upgrade/upgrade_server.sh
```

The script checks the installed v1.25 source, stops web/worker, makes a private migration backup, runs the regression suite against an isolated staged copy, backs up the replaced source, installs and restarts services. Expect several minutes and a temporary service interruption. Tests use fake providers; the installer removes OPENAI_API_KEY from the test process. If checks fail, code is not switched and the services restart. If the script reports unexpected/changed source, retain the error and reconcile the installed version; do not bypass the guard.

Private backup ZIPs contain sensitive account/data material. Keep them on the server in /home/superhuman/private-backups; they are not release attachments.

## 3. Configure explicitly before starting paid team work

Open https://superhuman.167-71-196-20.sslip.io/ and choose **Departments → Team & Twin**.

1. Initialize team records. This alone does not enable the team.
2. Open **Dollar budget and rates**. Create the first 30-day $200 period: Twin $60, specialists $80, hosted tools $20, unallocated reserve $40. Hosting and other outside subscriptions are separate.
3. Confirm an exact model identifier available to your API account and its current USD-per-million input/output rates, including applicable long-context rates. Use conservative upper rates when tiers differ. The inherited model label is a compatibility placeholder, not a claim of current availability. Do not copy the synthetic rates from tests. Add cards for any different models still used by legacy chat/research/drafting settings, or those calls will be blocked.
4. Return to Team settings, save that exact model identifier, keep maximum active assignments at 2 for the pilot, and enable the team. Existing department goal and worker-pause policies still apply.
5. Review employee charters, permissions and department writing rules/examples. Confirm initial Twin preferences under Memory. Create a small routine/internal project with clear acceptance criteria, then tell the Twin your current priorities.
6. Check that its task has one owner, a canonical run and an auditable result. Check a sensitive task stops for your approval. Inspect the dollar ledger and the provider's usage dashboard together.

Creating the first dollar budget activates the guard for existing model calls too, even while the team is disabled. An expired period does not automatically renew. Uncertain calls retain their reservation until explicitly reconciled with evidence.

The release has been validated locally, not installed or audited on your live server. Email, Slack and WhatsApp connections are not part of v1.26.

## Diagnostics

```bash
systemctl status superhuman-web.service superhuman-worker.service --no-pager
journalctl -u superhuman-worker.service -n 80 --no-pager
cd /home/superhuman/app
runuser -u superhuman -- .venv/bin/python -m superhuman.repairs.cli check
```

The installer prints the exact code-backup path. Retain it for rollback. Source verification after installation:

```bash
cd /home/superhuman/app
runuser -u superhuman -- .venv/bin/python /home/superhuman/superhuman-v1.26-upgrade/install_v126.py --check
```

On an already installed release this command checks installed checksums; it does not rerun the test suite.

## Rollback

Replace TIMESTAMP with the exact path printed during installation:

```bash
bash /home/superhuman/superhuman-v1.26-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.26-TIMESTAMP
```

Rollback refuses changed source or a damaged backup. It restores the 19 previous source files, removes the Team package, retains team data, artifacts, memories, accounting and audit records, and pauses the global worker. Team-owned canonical tasks are quarantined so v1.25 cannot resume them without Team governance. Other manual tasks retain their records. Do not resume paid work under v1.25 until you have inspected the retained budget and task state: the v1.26 dollar guard is absent after rollback. Reapplying v1.26 restores recorded canonical state conservatively, leaves the team disabled and requires owner inspection before continuation.
