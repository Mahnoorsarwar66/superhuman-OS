SUPERHUMAN v1.13 — UNIFIED INBOX BRIEFING

Upgrade the existing v1.12 server. The four established Gmail/Titan connections,
credentials, key, sync settings, .env, projects, conversation history and saved
emails remain in place. No new Google consent or provider permissions are added.

WHAT CHANGES
Open https://superhuman.167-71-196-20.sslip.io/briefing
- All four account reports on one page, ordered by their strongest priority.
- Read all connected inboxes with one button, with zero model requests for reads.
- Then explicitly request separate account reports, up to one model attempt per
  selected inbox. Four connected inboxes with previews means up to four attempts.
- New reports lead with attention items, decisions and follow-ups. Newsletter
  messages are grouped. Duplicate form submissions reuse their report requests.
- All displayed briefing dates use Pakistan time (PKT, UTC+5).
- Explicit past meeting times are placed under past-event follow-up, including
  meetings that pass after a report was generated. Billing/application deadlines
  can remain actionable even when overdue; they are not treated as past meetings.
- Emails have readable references such as E1, linked to saved report excerpts.
  Original identifiers stay out of the model context and ordinary briefing view.
- Concise prose is displayed first; longer validated explanations can be expanded.
- Useful local draft suggestions still wait for review/edit/approval in Talk.

GET STARTED AFTER INSTALLING
1. Open /briefing and confirm the four account labels and connected status.
2. Click Read 4 inboxes. Wait for the read jobs to complete and refresh.
3. Click Request 4 reports only after checking its model-attempt count.
   This uses currently SAVED excerpts; it does not wait for unfinished reads.
4. Refresh as the existing worker completes one report per account.
5. Open an Email E1/E2 source and compare with the original inbox.
6. Open Review report and proposed tasks. Approve only useful tasks after review.
Global worker pause applies as before. Existing optional 10-minute reads continue.
No paid scheduled briefing, push notification or automatic task approval is added.

OLDER REPORTS
Existing reports retain their original text in Talk, including details previously
included there. They are not rewritten or copied into the new dashboard layout.
Request new reports for the concise view. New follow-up discussion in an email
report uses that same account snapshot; other inboxes and general memory are not
added. Approved draft tasks still use normal workstream/memory routing as before.

SENSITIVE DETAILS AND COVERAGE
Recognised password/code labels, join links, tokens, UUIDs and long numeric/hex
identifiers are masked before excerpts are sent to the model. Masking also applies
to newly rendered report prose and saved source excerpts. This is best-effort
pattern matching, not a guarantee that every secret is detected. Some long numbers
that are not secrets can be masked too; verify precise amounts in the original.
Original saved emails, report snapshots and earlier replies remain private working
records; this is not a retrospective deletion or full-database encryption feature.

Read coverage is unchanged: INBOX only, last seven days, up to 25 candidate emails
per read; at most 12 saved excerpts per report, each body limited to 2,000 chars.
Attachments and large bodies are omitted. Source links show that saved excerpt,
not the full original email. A source still works after preview retention purges
its older message row. Read failures, coverage limits, stopped report attempts and
reports over twelve hours old are shown explicitly.

Sender identities, claims, urgency and meeting timestamps are not independently
verified. The model supplies the event interpretation. The code checks reference
membership and time format; it does not prove that the cited email supports a
claim. Email instructions never grant approval. No mail is sent, marked read,
starred, moved or deleted. No public-web research tasks are allowed from reports.

INSTALL FROM WINDOWS POWERSHELL
Extract the downloaded ZIP so this file is at:
C:\superhuman-os-starter\superhuman-v1.13-upgrade\README_V113.txt

Upload the EXTRACTED FOLDER with -r:

scp -r -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" "C:\superhuman-os-starter\superhuman-v1.13-upgrade" superhuman@167.71.196.20:/home/superhuman/

After that completes, connect to the server as root:

ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20

ONLY AT THE root@... SERVER PROMPT:

chown -R superhuman:superhuman /home/superhuman/superhuman-v1.13-upgrade
bash /home/superhuman/superhuman-v1.13-upgrade/upgrade_server.sh

No ZIP extraction command is needed on the server when you upload the folder.
The script checks dependencies and runs staged synthetic tests, stops the existing
services, saves a private bundle, installs guarded source changes and restarts
web/worker. If an intermediate action fails, its recovery trap restarts services.
The script does not log into inbox providers, make model requests or run tasks.
The restarted worker resumes the work and optional read schedules you previously
authorised. The test suite runs twice; allow several minutes on the 2 GB server.

All existing connections should still say Connected after restart. No credential
files need to be uploaded again. Keep the external mail key privately backed up.
Google Testing-mode token expiry and provider administrator policies are unchanged.

SOURCE AND DATA
Adds superhuman/briefing/ and patches five files: hosted/web.py, hosted/views.py,
mail/web.py, mail/store.py and dialogue/engine.py. Guards are based on the delivered
v1.12 ZIP, not on older temporary test snapshots. No database migration is needed;
validated report structure is saved with the existing conversation context.
No service, Nginx, firewall, domain, OAuth or environment settings are changed.
Do not rerun an older installer over this source. No new package dependency exists.

ROLLBACK IF NEEDED
First finish/cancel queued inbox-report messages in Talk and stop web and worker.
As superhuman, from /home/superhuman/app, run:

.venv/bin/python /home/superhuman/superhuman-v1.13-upgrade/install_v113.py --rollback /home/superhuman/app/backups/v1.13-TIMESTAMP

Use the exact backup directory printed during installation. The source guard
refuses changed installed or backup files. Rollback restores the five v1.12 files
and removes superhuman/briefing, retaining the DB, connections, key and reports.
New concise replies remain readable as text in Talk. Then restart both services.
Source-only rollback does not undo tasks you explicitly approved.

The supplied gmail_connect.py is the original v1.12 helper retained for regression
tests. You do not need to run it to install or use this release.
