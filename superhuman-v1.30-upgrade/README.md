# Superhuman OS v1.30 — Storage & Agent Foundation

Requires the installed v1.29 release. This package prepares the requested system baseline, Storage knowledge structure, personalities and proactive foundation. It does not claim to have audited the remote server before you install it.

## What's included

- Coordinator name The Twin; role/title Superhuman.
- Eight distinct, editable professional personalities, applied to employee conversations, specialist assignments, Twin coordination and communication analysis.
- Storage sidebar destination with seven departments and Shared facts. Existing files stay in place, awaiting explicit catalogue registration. Uploads cannot overwrite files.
- Document and fact records with project tags, topics, source/date, sensitivity, explicit agent grants, review dates and approval status. Metadata edits retain history; original file versions are not copied automatically.
- Approved shared facts and documents feed current conversations, context selection, assignments and existing workspace search/context lookup adapters. Bounded results include source/version/hash provenance. Cross-project and sensitivity limits apply to catalogue retrieval. Changed/missing files, due reviews and conflicting approved facts are withheld.
- Local system baseline: installed release, database check, worker heartbeat, team activation, model configuration, rate-card/period configuration, historical metered responses and channel sync evidence. Save and download snapshots. No automatic API probes or model calls.
- Proactive checks for managed task deadlines, stalled task-state updates, completed dependencies, ready results, existing communication alerts, active projects without open assignments, specialist concerns and conflicting facts. In-app signals are deduplicated and support acknowledgement, resolution and reopening.
- Per-rule controls for notification or Twin review. Notification is the initial default. Twin review uses the existing metered coordinator and never overrides existing governance.

## Installation from Windows PowerShell

First install v1.29 if you have not already done so. Extract this ZIP into `C:\superhuman-os-starter` so the folder below exists.

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.30-upgrade" root@167.71.196.20:/home/superhuman/
```

Then run this separate command in PowerShell:

```powershell
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 'chown -R superhuman:superhuman /home/superhuman/superhuman-v1.30-upgrade; bash /home/superhuman/superhuman-v1.30-upgrade/upgrade_server.sh'
```

The Ubuntu launcher checks service accounts and source compatibility, stops both services, makes a private data backup, validates staged code with offline tests, backs up changed source, installs atomically per file, restarts the services and captures a local baseline. It preserves credentials, data, existing pause settings and service configuration. If a preflight source check fails, do not force it: share the exact error.

## First use

Open Settings > System baseline, then Storage and Team > Personalities. Review Proactive checks and ACCEPTANCE-CHECKLIST.md. A saved past response or sync proves historical activity, not current connectivity. Completing real work is still required to establish end-to-end capability.

## Scope and limits

The catalogue adds retrieval controls for registered sources. Legacy, uncatalogued workspace files retain their previous departmental tool access until you register them. This is not a migration to a new physical file store or a complete replacement of existing identity/memory mechanisms.

Retrieval scans at most 50 eligible catalogue items and returns up to six bounded excerpts; automatic prompt context is smaller. Extraction supports the application's existing text/PDF/DOCX/XLSX/CSV/JSON formats. Scanned-image OCR, semantic indexing and independent fact verification are not included. Explicitly linked project records stay within their project. The Twin must be a named recipient (or covered by public/internal All agents sharing) for another department's catalogue records.

Proactive scanning runs at most once a minute when the existing worker is running and unpaused. It checks saved application state, not every external application. The stalled rule measures time since the assignment-state update; it is a check-in prompt, not proof the agent is idle. Scanning has no model cost. Selecting Twin review can cause existing coordinator calls within the current budget. No work starts outside existing permission, priority, sensitivity, risk and budget controls.

Personalities are editable instructions, not new models or fine-tuning. They do not grant human identity, expertise, authority or external access.

External action execution and its guidelines, the two larger integration/outcome gaps, questionnaires, detailed quality standards and additional ROI work are deferred. See ROADMAP-DECISIONS.md and EXTERNAL-ACTIONS-PROPOSAL.md.

## Checks without installation

On Ubuntu, from `/home/superhuman/app`, use the app virtual environment:

```bash
.venv/bin/python /home/superhuman/superhuman-v1.30-upgrade/install_v130.py --preflight
.venv/bin/python /home/superhuman/superhuman-v1.30-upgrade/install_v130.py --check
```

Preflight checks source and dependencies only. Check stages code and runs tests without changing installed code or data. Tests use local synthetic data and mocked provider/model responses.

## Rollback

Use the exact backup directory printed by the installer:

```bash
bash /home/superhuman/superhuman-v1.30-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.30-TIMESTAMP
```

Rollback refuses changed installed source. It restores v1.29 code, removes this release's package, retains saved catalogue/personality/baseline/signal records and uploaded files, and leaves work paused. The new pages are unavailable until v1.30 is installed again. Resume only after reviewing state. Earlier v1.29 rollback manifests remain tied to the earlier source hashes and should only be used after this release is rolled back.
