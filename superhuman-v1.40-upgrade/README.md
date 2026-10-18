# Superhuman OS v1.40 — Shared foundation and organisational awareness

Requires the installed v1.39 app. This is a guarded incremental upgrade, not a replacement app.

## What this fixes

The Twin and specialists were not reliably given a shared understanding of their owner, colleagues and mission. Direct chat policy also blurred internal saved-context access with unavailable external action tools. This installation supplies actual context through the existing governed model request boundary, rather than merely asking agents to sound informed.

- All eight employees receive the shared professional brief and current team directory in metered chat, local drafting, hosted research and coordination requests.
- The 25 imported records cover Mahnoor, Fawad, EdSync, Superhuman, hierarchy, collaboration, quality, research, initiative, revisions, interviews, the endorsement assignment and known unknowns.
- Relevant current department charters, writing rules, goals and supervision policies are retrieved fresh, with versions. Missing records are explicitly labelled.
- Permitted internal/public project summaries include current milestones and task states. Existing sharing and participant rules still apply; linked project rooms exclude other projects.
- Settings → **Shared foundation** lets you inspect, add, correct, classify and archive professional memory. All edits keep history and reject stale saves.
- Context previews make no model calls. Request receipts record the exact shared context supplied, its versions and linked cost record. Team conversation context links to this evidence.
- If the shared context changes during a model request, the result is rejected before it can become an actionable answer/decision. The provider cost remains accounted.

## Transfer scope

This is a curated transfer from the available project conversation, supplied memory summary and retrieved professional history as of 18 October 2026. It is not an export of all ChatGPT conversations, continuous memory sync, or model training. The import does not treat old business metrics as independently verified. Historical and unresolved records retain explicit labels. Exact 60-question option meanings and missing milestone definitions have not been invented.

Intimate family history, medical details, legal case evidence, credentials, bank documents and similar sensitive personal material were excluded from the team-shared seed. Use separately scoped storage for those. Existing private memory, inboxes and document grants are not broadened by this upgrade. Shared founder context is professional context, not a right to act on the owner's behalf.

## Install

Extract the ZIP into `C:\superhuman-os-starter`. Confirm it creates `C:\superhuman-os-starter\superhuman-v1.40-upgrade\upgrade_server.sh` (avoid an extra nested folder).

Windows PowerShell:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.40-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

Then run in the Ubuntu SSH window:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.40-upgrade
bash /home/superhuman/superhuman-v1.40-upgrade/upgrade_server.sh
```

The launcher selects `/home/superhuman/app`, checks source and service ownership, stops the services, takes a private backup, runs staged offline tests, installs and restarts. Unknown changed source is refused rather than overwritten. No new package dependencies, paid requests, activation, permission changes, budget increases or automatic resumes are part of installation.

## First checks

1. Confirm System health reports 1.40.0.
2. Open Settings → Shared foundation and review the imported records. Correct any business information that has changed.
3. Preview The Twin and each specialist. The directory must list all eight; current saved department instructions must be visible or explicitly missing.
4. In fresh conversations ask the exact questions from LIVE-ACCEPTANCE.md. Check the actual context receipt and answer, not merely a readiness badge.
5. Continue bounded test work. A successful memory import is not proof that team execution, research quality or the 80-page guide workflow has passed live QA.

## Rollback

Use the exact backup path printed by installation:

```bash
bash /home/superhuman/superhuman-v1.40-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.40-EXACT_TIMESTAMP
```

Rollback restores v1.39 source. Business records, spending, context receipts and owner memory corrections remain saved. The worker stays stopped/paused for inspection. Source edits made after installation cause rollback to refuse rather than overwrite them. A later v1.40 reinstall preserves existing memory corrections and archived records.
