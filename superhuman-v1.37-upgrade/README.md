# Superhuman OS v1.37 — Trust and workflow repair

Upgrade from the installed v1.36 application. This package repairs the live-audit findings; it does not activate autonomous employees, authorize a budget, change model rates or grant external actions.

## Changes

- Paid calls through the application’s shared model client now block before provider dispatch when no dollar budget is configured. Existing exact-model rate, expiration, hold, pool, concurrency and per-task controls remain enforced. Metered usage records and conservative reservations remain authoritative; unavailable usage retains its reservation. Older unmetered charges are not fabricated or labelled zero.
- Fix the empty/whitespace-only internal Storage search that broke current deliverable checks. Preserve user-facing strict search validation, content hashes and historical approval records. Stored findings are separate from current checks.
- Choose milestones with a department lead when creating a project, or choose tasks first. Milestone setup is also visible in the work plan. Existing open tasks remain protected against silent conversion; the management view links to them. No task is cancelled by this upgrade.
- Prefill project outcome and success criteria in the interview. Blank answered fields are not stored as facts; existing blank rows display as unanswered. Non-empty research requests count as recorded answers. Existing confirmed briefs and histories are retained.
- Generic milestone instructions no longer refer to Katherine or the endorsement guide. The actual endorsement blueprint and its controls are retained.
- Team compatibility entry points and contextual tabs use the current hub. Readiness explicitly distinguishes disabled coordination and missing budget setup from an idle worker. Archived conversations disable their composer as well as retaining server-side enforcement.
- Refresh portrait URLs and apply explicit visibility/size/overlay rules while preserving all eight original image files. Portrait appearance still needs a live visual check; the audit did not establish the exact rendering cause.
- Project activity displays PKT. Review links focus the selected output. Pasted iCalendar events retain their own SUMMARY titles, including folded/escaped text. Export capability help is consistent.
- Best-effort masking of labelled credential values in Inbox list/detail previews. Original saved messages are retained. This is not a complete secret detector and does not revoke or rotate any credential.

## Install from Windows PowerShell

Extract `superhuman-v1.37-upgrade.zip` into `C:\superhuman-os-starter` so it contains `C:\superhuman-os-starter\superhuman-v1.37-upgrade\upgrade_server.sh`.

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.37-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

Then run these **in the Ubuntu SSH window**, where the prompt begins `root@ubuntu...`:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.37-upgrade
bash /home/superhuman/superhuman-v1.37-upgrade/upgrade_server.sh
```

The launcher checks the service account and installed source, stops web/worker, creates a private data backup, runs staged synthetic checks and installs only recognized v1.36 source. It restarts the existing services. It does not install dependencies or modify authentication/Nginx/service definitions. Allow the displayed test run to finish.

If it reports **Unrecognised v1.36 source**, it stops without overwriting the file. Share the filename/error; do not remove the source guard or copy files over manually.

## After installation

1. Hard refresh the portal. Settings → System baseline should report v1.37.0.
2. Open Settings → Budget. Configure an explicitly chosen dollar period and confirm current exact-model rates if they are missing. The installation deliberately does not authorize spending for you. Previously working unconfigured chats will now block until this is done. A disabled Team still requires separate activation before autonomous coordination.
3. Resume the retained `QA-AUDIT` project. Verify portrait rendering, a valid stored draft’s current checks and one small chat with a matching cost record before more paid testing. Earlier audit spending must be reconciled using provider usage, not guessed.
4. Complete the remaining bounded acceptance run: specialist work → independent review → lead integration → Twin → owner milestone decision, intentional revision/retry, downloaded Word/PDF inspection and budget reconciliation. The package’s mocked-provider tests do not prove live business-output quality.
5. Privately replace the credential seen in the saved Inbox if it remains current. Preview masking does not invalidate a password or remove the source email.

## Rollback

Use the exact backup printed by installation, for example:

```bash
bash /home/superhuman/superhuman-v1.37-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.37-EXACT_TIMESTAMP
```

Rollback restores code only and retains business records, approvals, conversations, budgets and image files. It refuses changed installed files or changed backups. It pauses the worker and restarts only the web service: v1.36 contains the old unconfigured-budget bypass, so inspect before resuming paid work. No database restore is performed automatically.

## Scope and limitations

No live portal changes were made while preparing this package. No real API spend is required by its tests. Custom CLI/orchestrator files are retained; independently customized code calling a provider directly is outside the shared-client guard. The full old 1,033-test suite was not rerun: the supplied runner selects repair tests and existing governed-team, milestone, assurance and practice tests, with synthetic providers. Exact results appear in VALIDATION.md.

Existing tasks are not automatically mapped into milestones, missing departmental objectives/source evidence are not invented, and the two deferred gaps—conversation-to-completed-work reliability and measured initiative/business ROI—remain acceptance work. The installation does not implement new external sending authority or eight continuously thinking processes.
