SUPERHUMAN v1.12 — PRIVATE MULTI-INBOX PILOT

Install over the tested v1.11 app. This is a code upgrade for your existing
DigitalOcean deployment, not a new public app or a ChatGPT email connection.

Four fixed labels: Personal Gmail, EdSync Gmail, EdSync Titan, NextSTEP Gmail.
Credentials, provider message identities, sync state and report snapshots are
separate per inbox. Gmail uses OAuth with exactly gmail.readonly. Titan uses
verified SSL IMAP, EXAMINE and BODY.PEEK. No mail mutation or sending exists.

Open CONNECTION_GUIDE.txt for exact Windows PowerShell and Ubuntu commands.
Install first, then connect Titan, then authorise/import the three Gmail accounts.
You do not need to supply any passwords or tokens in chat.

READS AND REPORTS
Manual reads cost zero model requests. Optional reads every 10 minutes default
off. The persistent worker handles these alongside existing conversations and
approved tasks. Global worker pause stops all these activities.
Read coverage is intentionally bounded: recent INBOX previews, not a complete
email archive or urgent-message notification service. See the connection guide.

A report sends up to twelve excerpts from ONE inbox to your configured model.
Reports run through the existing Talk queue with an initial one-attempt budget.
General memory, other inboxes and workstream project listings are excluded from
report context, including follow-up discussion in that report thread. The report
is a model draft based on unverified email claims and possibly truncated text.

Suggestions stay proposed until the owner reviews/edits and approves them.
Only local draft tasks can be proposed by inbox reports; public-web research
proposals are rejected to avoid searching with private email contents.
Existing approval logic atomically creates one task, with a separate budget of
up to three model attempts, even if the approval request is repeated.
Approved tasks use the chosen existing workstream and normal memory rules.
No new memory notes are inferred or confirmed from email automatically.

SECURITY AND DATA
Keep the server and deployment backups private. Long-lived credentials are
encrypted; the key lives in ~/.config/superhuman/mail.key, outside transfer
bundles. Back up that key separately or reconnect accounts after losing it.
Saved previews/reports are private working data in the existing database and
are not separately encrypted by this release.
The existing login, exact-origin boundary, CSRF and inert rendering still apply.
The local Gmail helper opens the normal browser with PKCE, state and a random
127.0.0.1 callback. Temporary credential files must be imported and removed.
The server removes its transfer copy after successful encrypted import.

FILES
upgrade_server.sh: root-only deployment orchestration for this server.
install_v112.py: source guard, isolated staged checks, install/idempotence/rollback.
gmail_connect.py: standard-library laptop OAuth helper; no Google password.
restore_bundle.py: standard-library restore helper for v1.12 private bundles.
requirements-v112.txt: the added server cryptography dependency.
superhuman/mail/: store, vault, read-only providers, CLI and inbox UI.
reference/: delivered v1.11 source basis, not application replacement files.
tests/: current regression and new synthetic mail checks; no live inbox access.

ROLLBACK
Stop both services before a manual rollback. Complete or cancel queued/running
inbox-report messages in Talk first. Run from /home/superhuman/app, as superhuman:

.venv/bin/python /home/superhuman/superhuman-v1.12-upgrade/install_v112.py --rollback /home/superhuman/app/backups/v1.12-TIMESTAMP

Use the exact backup path printed during installation. The guard refuses changed
installed source or backup files. It restores the five patched Python files and
removes superhuman/mail. Mail/conversation records, credentials, the external key,
.env and existing projects remain. The older app does not display the retained
mail tables. The dependency is not uninstalled. Restart the original services
after successful rollback. Nothing is sent or restored over your live database.

THIS BUILD HAS NOT CONNECTED TO YOUR DROPLET OR LIVE PROVIDER ACCOUNTS.
Google consent, business administrator policy and Titan third-party-client access
must be verified with your real accounts after installation.
