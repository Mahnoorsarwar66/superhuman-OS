# v1.26 installation compatibility repair

For the reported error: `Unrecognised v1.25 source: cli.py; nothing overwritten`.

Your supplied v1.25 CLI delegates task execution to `core/orchestrator.py`. The original upgrade expected the starter CLI, which called the provider directly. This repair recognises the two reviewed CLI profiles, preserves the supplied production CLI's commands and database schema, and meters the actual provider call in its companion orchestrator. SDK automatic retries are disabled for that call. Approval-required tasks still return before contacting the provider.

The repair retains source guards. Only the reviewed production CLI/orchestrator pair or the existing starter profile is accepted. Unknown code changes remain refused. The optional orchestrator is included in backups, checksums and rollback. No user database, credential, service configuration or installed app source is manually replaced by the preparation script.

## Run from Windows PowerShell

Extract the ZIP to:

`C:\superhuman-os-starter\superhuman-v1.26-compatibility-fix`

Run these two commands in PowerShell:

```powershell
scp -r -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" "C:\superhuman-os-starter\superhuman-v1.26-compatibility-fix" superhuman@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 "bash /home/superhuman/superhuman-v1.26-compatibility-fix/run_repair.sh"
```

The second command runs on Ubuntu automatically. Do not type chown, sed or Ubuntu paths directly into PowerShell.

The launcher first checks and updates only recognised files in the extracted `/home/superhuman/superhuman-v1.26-upgrade` package, preserving original installer files under its compatibility-backups directory. It then runs the normal v1.26 installer, including isolated tests, app-source backup and service handling. Only if v1.26 succeeds does it run the already-uploaded v1.27 installer. If v1.27 is not present it reports that v1.26 succeeded and asks you to upload v1.27. Any failure stops the sequence; retain its output rather than bypassing a guard.

The repair contains the Gmail helper required by inherited installation tests. It does not alter v1.27 or reset the dollar budget. The full v1.26 download has also been updated to include this compatibility support, so fresh installations can use that package directly.

## Validation

Ten added regression cases cover the supplied legacy commands/review history, both recognised profiles, unknown-source rejection, optional-file backup selection, migrated source recognition, actual legacy-provider dollar metering, insufficient-budget refusal, Team-paused budget enforcement, and the pre-provider approval gate. The package preparation was checked for idempotency and rejection of unknown installer edits. The repaired installer passed 624 staged tests. Production-profile rollback restored all 20 source files exactly and retained the legacy task/review database. The resulting v1.26 installation also passed v1.27 preflight. These checks used a local reconstruction of the files you supplied. No live server access or paid model request was used.
