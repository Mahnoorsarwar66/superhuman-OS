# Superhuman OS v1.28 — Coherent Workspace & Team Room

This is a single upgrade from the delivered v1.27 release. It preserves the existing SQLite records, inbox credentials, memory, projects, writing skills, dollar budget, employee permissions and service configuration. It does not install v1.26 or v1.27 for you. An unrecognised baseline is rejected before installed files are overwritten.

## Install from Windows PowerShell

Extract the ZIP into `C:\superhuman-os-starter`. The resulting folder should be `C:\superhuman-os-starter\superhuman-v1.28-upgrade` and contain `upgrade_server.sh` directly.

Run these two commands in **Windows PowerShell**. They use the SSH key that already worked in your previous connection:

```powershell
scp -r -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" "C:\superhuman-os-starter\superhuman-v1.28-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 "bash /home/superhuman/superhuman-v1.28-upgrade/upgrade_server.sh"
```

The tests can take several minutes on the 1 CPU server; leave the SSH window open until the final service checks appear. The second command runs the Ubuntu commands on the server. Do not run `chown`, Linux app paths or `bash /home/...` directly inside Windows PowerShell.

The server launcher checks the exact source and existing dependencies, stops web/worker, creates a private app/data backup, tests the staged upgrade in a temporary workspace, and installs/restarts only after the checks pass. It retains the existing origin, authentication and service files. It makes no model calls. Keep the backup private; it can contain your data and credentials. If a check fails, share the final error lines, never `.env`, keys, tokens or the private backup.

Open https://superhuman.167-71-196-20.sslip.io/ and refresh the page after installation.

## What changed

1. **Work briefing:** remains in the Overview navigation section. The existing briefing URL and data remain valid.
2. **Speech:** microphone dictation on the existing Talk composer, Twin owner-update composer, and new Team Room composers. English and Urdu selectors; text stays editable and is never sent automatically. Unsupported browsers show a typing fallback. Browser support, microphone permission and recognition-language availability vary. Browser recognition may process audio online. There is no new paid server transcription service.
3. **Departments:** existing six tabs remain. Agent and Supervision are added inside each department. The global Departments / Priorities / Supervision tab strip is removed. Plan & Priorities remains department-specific.
4. **Project conversations:** new project chats carry an explicit project association. Two projects in the same department have separate lists and prompt context. Existing conversations remain at department level until you explicitly link one. Inbox reports cannot be linked. Linking is permanent in this release; choose a conversation that belongs entirely to the project, including its past messages. Pending chats cannot be linked.
5. **Inbox:** accounts and connection status, a message list with search/review filters, and a selected message with saved Twin assessment and local reply drafts. Read access, AI consent and actual last check are distinct. Local review state does not change read/unread state at the provider. Opening Inbox does not sync, analyse or grant consent. Search covers the latest 5,000 saved previews. Use Personal assistant to request analysis and manage connections.
6. **Tasks:** no Tasks entry in the main sidebar. Projects contains All tasks and Suggested work. Existing task processing and outstanding legacy jobs are retained; diagnostic worker/legacy controls are under Settings. Coding stays directly accessible in the sidebar.
7. **Calendar:** Month / Week / Day / Agenda views, with a 24-hour week/day grid, overlap lanes and day rollover in Asia/Karachi (PKT, UTC+5). Existing meeting details, exports, planning deadlines and review screens remain accessible. The calendar is local; it does not synchronize a Google Calendar account or send invitations.
8. **Team Room:** conversations with the Twin and specialists, separate project rooms, and a feed of actual saved employee handoffs, questions, challenges and decisions. No simulated conversations or private model reasoning. Owner updates remain a separate explicit control. Chat proposals create restricted, consequential tasks in a governed project; they retain subsequent Twin, owner, budget and permission checks. Chat cannot approve external actions.
9. **Names:** Jose, Chris, Sam, Sarah, Amelia, James and Katherine; Mahnoor Twin remains the coordinator. Employee IDs, histories and writing skills are preserved. Names are applied once on worker startup.
10. **Employee board:** distinct bot cards with saved status, current assignment/project, last recorded action, wait/block reason, chat and control links. Working status requires both a current worker heartbeat and a running record. Merely dispatching work does not mark an employee as working. Status refreshes while the board is open; this does not create eight simultaneous model executions.

## Meeting intake

The worker scans the latest 1,000 saved communication previews after a successful intake cycle; you can also press **Calendar → Invitation intake → Scan saved previews**. This parser uses no model requests. It recognises explicit ISO dates near meeting intent and common iCalendar DTSTART/DTEND instants in saved text. Paste invitation / `.ics` text for review, or use New meeting for other formats.

Dates with offsets are converted accurately to PKT. IANA zones such as `America/New_York` use daylight-saving rules. Missing/ambiguous zones and repeated DST hours require a choice. `PST` denotes Pacific Standard Time, while Pakistan time is labelled `PKT`. Conflicting seasonal abbreviations are rejected.

Intake proposes events; you confirm them before they enter the calendar. Changes to an invitation generate a new proposal and never overwrite a confirmed event silently. Check for reschedules, cancellations and duplicates before confirming. Unsupported natural-language dates, all-day `.ics` fields, attachments, recurrence expansion and calendars not connected to the current intake require manual entry. A recurring invitation imports only the reviewed occurrence. Unknown end times are labelled; the day/week view uses a small visual placeholder and does not invent a stored duration.

## Employee mapping

| Department | Employee |
| --- | --- |
| US Graduate Applications | Jose |
| Investors, Grants & Partnerships | Chris |
| Legal & Operations | Sam |
| EdSync Sales & Marketing | Sarah |
| Career Algorithm R&D | Amelia |
| EdSync Product & University Pilots | James |
| UK Innovator Founder | Katherine |
| Coordination & personal assistance | Mahnoor Twin |

## After installation

Use `ACCEPTANCE-CHECKLIST.md` for the live check. Local test results cover synthetic data and mocked model/provider responses. They do not prove your live connections, browser microphone, server services or model account are working.

New authenticated static CSS/JavaScript supports dictation and status refresh. Inline scripts and eval remain blocked; no remote assets are loaded. Only this site's microphone permission is requested, after you click Dictate.

## Rollback

The successful installer prints an app code-backup path such as `/home/superhuman/app/backups/v1.28-TIMESTAMP`. To restore v1.27 code, run from Windows PowerShell, replacing the path with the exact printed path:

```powershell
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 "bash /home/superhuman/superhuman-v1.28-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.28-TIMESTAMP"
```

Rollback verifies source checksums before restoring. User data, room associations, confirmed meeting imports, names and governed tasks are retained. Queued/running Team Room replies are cancelled to prevent replay under the older department-level prompt. The worker remains paused for inspection; use the existing worker controls to resume after reviewing the retained work. This is a code rollback, not a deletion or data restoration.

## Optional manual source checks (Ubuntu app directory only)

```bash
/home/superhuman/app/.venv/bin/python /home/superhuman/superhuman-v1.28-upgrade/install_v128.py --preflight
/home/superhuman/app/.venv/bin/python /home/superhuman/superhuman-v1.28-upgrade/install_v128.py --check
```

Run these as the `superhuman` user from `/home/superhuman/app`; the launcher handles that automatically during installation.
