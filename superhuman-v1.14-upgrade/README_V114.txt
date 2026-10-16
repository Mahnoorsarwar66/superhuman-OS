SUPERHUMAN v1.14 — RESUMABLE INBOX READS AND REPORT COVERAGE

Install over v1.13. All four connections, OAuth grants, credentials, external
mail-encryption key, .env, projects, approvals and reports are retained.

WHAT TO DO AFTER INSTALLING
Open https://superhuman.167-71-196-20.sslip.io/briefing
Click Read inboxes ONCE. The worker queues subsequent read batches automatically
until the current scoped scan finishes, stops with an error, or hits capacity.
You do not need to repeatedly click Read to get past the old 25-message preview.
Refresh to see progress. Background reads use zero MODEL requests; provider API
reads still occur. Existing global Pause and opt-in 10-minute reads apply.

Each account shows:
- Saved previews currently retained locally.
- Excerpts included in completed model reports.
- Excerpts reserved by queued/running reports.
- Excerpts waiting for a report.
- Discovered candidates processed, saved this scan and unavailable/outside-window.
- Scan state and exact window in Pakistan time.
"Discovered" is not the provider's full inbox count while pagination is in progress.
"Included" does not mean you read the email, the model understood every detail,
or the email was marked read remotely.

Request next reports explicitly when ready. Each selects up to 12 waiting emails
per account. A repeated submission of the SAME form returns its existing request.
Separate new requests reserve different waiting emails, even while another report
is running. Failed, interrupted, cancelled or budget-blocked reports release their
reservations. They are not retried automatically. Each report attempt counts and
has the same cost/budget rules as v1.13. Tasks still need separate owner approval.
When no saved emails are waiting, no new model request is queued for that account.
Older completed reports are indexed locally to avoid resubmitting their excerpts.

SYNC DETAILS
A scan freezes a seven-day INBOX window when it begins. Gmail page tokens and
pending IDs are saved, including progress within a page. Titan uses a frozen UID
list and UIDVALIDITY, with read-only EXAMINE, metadata and BODY.PEEK fetches.
Titan's date-based search is refined with INTERNALDATE to the exact frozen window.
A UIDVALIDITY change resets its pending namespace safely. Messages arriving after
the frozen window belong to the NEXT scan, not to this scan's coverage claim.
After a completed scan, another manual read or opted-in scheduled read starts a
new window. Known remote IDs are skipped without repeatedly downloading bodies.

Each pass processes up to 25 new candidates, up to 250 cached-ID skips, at most
five Gmail discovery pages and a bounded time slice. Cursor + saved message +
remote identity commit atomically. Successful earlier messages remain saved after
a later provider failure. A process restart does not lose committed progress.
Read continuations share the existing worker fairly with conversations/tasks.

A complete state means that this scoped discovery list/pages were traversed. It
does not mean all account folders, full bodies, attachments or future arrivals
were read. Deleted/unavailable IDs and out-of-window messages are counted. Large
bodies remain headers-only, preview bodies are limited, and report excerpts still
stop at 2,000 characters. Source links and sensitive-data masking work as before.
Small MIME messages may transfer attachment bytes in memory with the email;
attachment content is discarded, not extracted, saved or supplied to reports.
Provider pagination is not a transaction over a changing remote inbox.

Titan discovery is capped at 50,000 candidate IDs per scan. Exceeding it shows
scope_limited, never complete. Very large server SEARCH responses can also stop
with a visible error rather than a false completeness claim.

RETENTION AND CAPACITY
Up to 5,000 previews per account are retained by the new reader. It never removes
an unreported preview merely to make room. At capacity, previews already supplied
to completed reports can be removed; their immutable report excerpts and remote
identity remain. If no safe room exists, the scan pauses with capacity_blocked.
Complete some reports, then click Read again. The stored cursor resumes.
Historical items already pruned by older releases cannot be retroactively mapped
from their local IDs to provider IDs; a first rescan can reimport such items.

ERROR RECOVERY
A read error retains committed progress and stops immediate continuations. Fix
the connection if needed, then click Read to retry from that point. If a Gmail
page token expired and retrying Read still fails, open the inbox's coverage panel
and choose Restart scoped scan. This starts a new seven-day window, keeping saved
emails, report history and known-ID deduplication. Restart refuses while a read is
actively running. Disabled automatic reading stays disabled. No paid reports are
started by retry, restart or scan completion.

INSTALL — WINDOWS POWERSHELL
Extract so the folder contains:
C:\superhuman-os-starter\superhuman-v1.14-upgrade\upgrade_server.sh

scp -r -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" "C:\superhuman-os-starter\superhuman-v1.14-upgrade" superhuman@167.71.196.20:/home/superhuman/

After the upload completes:

ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20

ONLY AT THE root@... SERVER PROMPT:

chown -R superhuman:superhuman /home/superhuman/superhuman-v1.14-upgrade
bash /home/superhuman/superhuman-v1.14-upgrade/upgrade_server.sh

The script performs fast dependency/source preflight, stops the existing services,
saves a private backup and runs the full staged suite ONCE before changing source.
If tests or an intermediate step fail, original services are restarted. The app
is temporarily unavailable during these checks. No paid calls or live provider
requests occur in the tests. Existing authorised work/reads resume after restart.
No new package dependency, firewall, Nginx, domain or OAuth setup is needed.

CODE AND DATA
Adds superhuman/mailflow and guards five v1.13 files: mail/store.py,
mail/providers.py, mail/web.py, briefing/web.py and hosted/web.py. The delivered
v1.13 source is the reference. Additive SQLite tables store scan progress, durable
identities and report membership. Historical report indexing is local and does not
call the model. Original mail/conversation tables and snapshots remain intact.
Credentials stay encrypted with the existing external key. Working mail data and
private deployment backups retain the privacy rules of earlier releases.
The Gmail connector helper is included only for existing regression checks.

ROLLBACK
Stop services first and finish/cancel queued inbox reports before code rollback.
From /home/superhuman/app, as superhuman:

.venv/bin/python /home/superhuman/superhuman-v1.14-upgrade/install_v114.py --rollback /home/superhuman/app/backups/v1.14-TIMESTAMP

Use the exact backup path printed during installation. Code rollback retains the
new tables and all working data. A safety guard refuses rollback if any inbox has
more than 500 previews, because the older reader could trim them. Keep v1.14 and
prepare a safe archive/retention migration in that case. Do not delete unreported
emails to bypass this guard. Source and backup drift also block rollback.
Then restart services after a successful rollback. Do not rerun an older installer
over this release. Keep the external mail key backed up separately as before.
