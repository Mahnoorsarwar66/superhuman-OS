SUPERHUMAN v1.10.0 — EDITABLE MEMORY, FEEDBACK AND WORK BRIEFING

This upgrade adds explicit, versioned owner memory to the existing authenticated
web app. It installs code; it does not deploy to your server automatically.

WHAT CHANGES
- Memory navigation on phone and laptop: save facts, decisions, preferences,
  feedback and updates, grouped by workstream.
- Notes start Proposed. Choose Confirmed when the note should become eligible
  for model context. Confirmation records your acceptance; it does not prove
  the information is factually correct or independently verified.
- Edit notes with conflict protection and version history. Archive superseded
  notes to remove them from future context. History and previously generated
  artifacts retain old text: Archive is not a purge/delete operation.
- Source type and reference, optional expiry, task genre and Sensitive flag.
  Sensitive notes are visible to the signed-in owner but never automatically
  sent to a model. Do not save passwords, keys or credentials as notes.
- Context preview shows the actual selector used by drafting, research and
  larger-objective planning. Only relevant confirmed, unexpired notes in the
  selected workstream/global scope are eligible. Non-preferences require a
  topical keyword match; preferences can apply without one. Genre limits apply.
  At most eight new notes, with bounded context; notes that do not fit are
  omitted whole and identified in selection details. This is deterministic
  retrieval, not semantic/vector search, and can miss a relevant note.
- Work pages link to a separate feedback form. Saving feedback does not approve,
  retry or alter the task. Choose Feedback as the note type where appropriate.
- Work briefing shows current unfinished projects and recent confirmed updates,
  decisions and feedback. It is a saved-state view, not an AI-generated report.
- Existing legacy identity/memory remains intact and separately managed. No
  automatic import, duplication, or reinterpretation of prior private records.
- Future generation uses the current note versions at execution time. Preview
  reflects current state, not a frozen promise about queued work; notes can
  change before execution. Generated task traces include note IDs, versions,
  source references and content hashes. Editing a note does not revise old work.

DEPLOYMENT FIXES INCLUDED
- Same-origin referrer policy so browser form posts retain their origin.
- Favicon returns 204 without creating/replacing a login session.
- Removes only the temporary CSRF diagnostic prints issued during setup.
- Private transfer bundles exclude *.runtime.lock and retain SQLite snapshots.
- Invalid structured reviews remain blocked and report their actual validation
  reason. Reviewer prompts distinguish internal checks from draft evidence.
  This does not remove quality gates or promise that model reviews will pass.

NOT INCLUDED
A free-form AI chat, voice, automatic inbox ingestion, Gmail/WhatsApp/Slack/
calendar/LinkedIn integrations, scheduled briefings, automatic research/task
creation, file reorganisation, multi-user accounts, model retraining or self-
modifying code. A saved update is a memory note; it does not create a task.
External integrations remain later milestones. Saving, editing and previewing
notes use zero model calls. Drafting/research still use existing request budgets.

INSTALL ON THE EXISTING DIGITALOCEAN SERVER (AUTHORITATIVE DATA)

1. Extract the ZIP on Windows so this file is at:
   C:\superhuman-os-starter\superhuman-v1.10-upgrade\README_V110.txt
   This folder contains only the upgrade, not a copy of your project database.

2. WINDOWS POWERSHELL prompt (PS C:\...>): upload the upgrade:

   scp -r -i "$env:USERPROFILE\.ssh\superhuman_replacement" C:\superhuman-os-starter\superhuman-v1.10-upgrade superhuman@167.71.196.20:/home/superhuman/

3. WINDOWS POWERSHELL: connect as root:

   ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20

   Commands below run ONLY at the server's root@...:~# prompt.

RECOMMENDED SHORTCUT
At the root SERVER prompt, run:

   bash /home/superhuman/superhuman-v1.10-upgrade/upgrade_server.sh

This script performs steps 4–7 below: staged checks, graceful service stop,
private data backup, source installation and service startup. On failure after
stopping, it attempts to bring the existing services back. It does not change
Nginx, TLS, origin or credentials. Do not run steps 4–7 again after it succeeds.
If the shortcut reports an error, share the output before attempting manual
steps. A code rollback is separate, explicit and checksum guarded.

MANUAL ALTERNATIVE (instead of the shortcut)
4. Check compatibility while the service is still available:

   runuser -u superhuman -- sh -c 'cd /home/superhuman/app && .venv/bin/python /home/superhuman/superhuman-v1.10-upgrade/install_v110.py --check'

   The installer stages installed Python source in a temporary directory, applies
   narrow source patches there and runs included tests with fake model responses
   and temporary data. It does not copy/use .env or call a model. No production
   notes, project records, credentials, origins or services are modified by check.
   If the check fails, stop and share its output. Do not install over a failure.
   Known original v1.9 source and the exact fixes made during setup are supported;
   unexpected code changes are refused. Reference source is checked as AST on
   the installing Python to avoid Python-version fingerprint mismatches.

5. After checks pass, stop services gracefully. This may wait for a running task:

   systemctl stop superhuman-worker.service superhuman-web.service

   Make a private backup under the app owner's home (not /root):

   runuser -u superhuman -- sh -c 'mkdir -p /home/superhuman/private-backups && chmod 700 /home/superhuman/private-backups && cd /home/superhuman/app && .venv/bin/python -m superhuman.hosted.cli bundle --output /home/superhuman/private-backups/pre-v110-$(date -u +%Y%m%dT%H%M%SZ).zip'

   If backup fails, do not install. Restart the old services, then diagnose:

   systemctl start superhuman-web.service superhuman-worker.service

   Each backup filename must be new. Backups contain private source/data and
   password hashes, not .env. Copy backups off the Droplet for durable recovery;
   a second copy on the same Droplet is not protection against Droplet loss.

6. Only after backup succeeds, install as the app owner:

   runuser -u superhuman -- sh -c 'cd /home/superhuman/app && .venv/bin/python /home/superhuman/superhuman-v1.10-upgrade/install_v110.py'

   The same tests rerun before writing. It backs up six changed Python files,
   adds superhuman/knowledge and retains the rest of your source and all data.
   No extra dependencies, environment keys, Nginx, systemd or TLS changes.
   If installation reports a failure, existing source is retained or rolled back.
   Restart existing services even after a failed check/install before leaving.

7. Restart and verify:

   systemctl start superhuman-web.service superhuman-worker.service
   systemctl is-active superhuman-web.service superhuman-worker.service

   Both should show active. Refresh:
   https://superhuman.167-71-196-20.sslip.io/memory

   Existing owner credentials and HTTPS hostname remain in use. An old open
   page may need a reload. The Memory link should be visible after refresh.

FIRST VERIFICATION (NO API CALLS)
- Save a harmless test note: Workstream marketing, Type fact, Title University
  discovery, Content "For university discovery meetings, keep suggestions
  separate from confirmed commitments.", Status Confirmed, not Sensitive.
- Open Preview task context. Workstream marketing; task "University discovery
  agenda". Confirm the saved note appears with its ID/version in selection.
- Edit its wording. Check that version 2 and both historical versions appear.
- Archive it, then preview again. It should no longer be selected.
- A different workstream must not select a marketing-only note.
- Proposed, Sensitive, expired and different-genre notes must not be selected.
- Inspect the work briefing and feedback link on a task page.
Only after these local checks, try one ordinary draft task if desired. That
uses your normal API budget. Review output; memory retrieval does not guarantee
factual or semantic correctness.

ROLLBACK (CODE ONLY; RETAINS MEMORY NOTES)
Stop both services as in step 5. The installer prints its backup directory,
for example /home/superhuman/app/backups/v1.10-<timestamp>. Run:

   runuser -u superhuman -- sh -c 'cd /home/superhuman/app && .venv/bin/python /home/superhuman/superhuman-v1.10-upgrade/install_v110.py --rollback /home/superhuman/app/backups/v1.10-REPLACE_WITH_ACTUAL_TIMESTAMP'

Then start both services. Rollback refuses if source changed since installation.
It restores only the six Python files and removes the new knowledge package;
it does not restore/delete databases. Notes remain in data/knowledge/notes.db
for a later reinstallation. Do not delete backups or data to work around errors.

LOCAL WINDOWS INSTALL (OPTIONAL, NOT REQUIRED FOR CLOUD OPERATION)
Keep the server's data authoritative. Do not copy an old Windows database over
it or operate two workers on copied data. To update source on Windows separately,
stop local dashboards/workers, activate .venv, cd C:\superhuman-os-starter and run:

   python C:\superhuman-os-starter\superhuman-v1.10-upgrade\install_v110.py --check
   python C:\superhuman-os-starter\superhuman-v1.10-upgrade\install_v110.py

This changes local code only and does not synchronise cloud memory.
