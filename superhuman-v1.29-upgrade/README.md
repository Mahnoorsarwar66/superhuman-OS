# Superhuman OS v1.29 — Connected Workspace

One installation addressing the UX review over the delivered v1.28 release. This package preserves the existing records, employee IDs and names, writing skills, budgets, inbox credentials, origin and service files. It does not modify your live server until you run the server installer.

## Install from Windows PowerShell

Install v1.28 first if it is not already installed. This upgrade recognises the delivered v1.28 source; it refuses unknown or edited integration files before overwriting installed code.

Extract this ZIP into `C:\superhuman-os-starter`. The resulting folder must contain `C:\superhuman-os-starter\superhuman-v1.29-upgrade\upgrade_server.sh` directly.

Run these two commands in Windows PowerShell:

```powershell
scp -r -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" "C:\superhuman-os-starter\superhuman-v1.29-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 "bash /home/superhuman/superhuman-v1.29-upgrade/upgrade_server.sh"
```

The second command runs Linux commands on the Ubuntu server. Do not paste `/home/...` commands directly into Windows PowerShell. The SSH window will show the staged tests; they may take several minutes on your 1 CPU server. Keep it open until the service checks finish.

The launcher checks the baseline, stops the web/worker services, creates a private app/data backup, runs the full staged regression suite, installs only after success and restarts services. It makes no model requests. Keep the backup private because it can contain data and credentials. If installation fails, share the final error lines, not the backup, `.env`, keys or tokens.

Open https://superhuman.167-71-196-20.sslip.io/ after completion and refresh the page.

## Changes from the UX review

| Issue | v1.29 behaviour |
| --- | --- |
| Department totals omit employee work | Departments include Team business projects and tasks, and link to their actual controls. A task's underlying execution is excluded from duplicate project/task counts. |
| Two competing project creation flows | Overview, Projects and department actions lead to one managed project form. Earlier execution records remain available as earlier work, without becoming a second normal creation choice. Old POST endpoints remain compatible with existing integrations. |
| Fragmented Twin screens | Team has Mahnoor Twin, Conversations, Employees and Activity. The Twin workspace has Chat, Owner updates and Communications tabs. Old Twin and assistant landing URLs redirect into it; existing detail/settings URLs remain valid. |
| Twin chat lacks communications context | Global Twin chats can receive up to three saved briefing summaries whose entire source set is still enabled, consented, available and unchanged. No live inbox fetch happens when you open a chat. Project chats deliberately exclude global inbox summaries. Revoking consent during a reply invalidates that response before saving. |
| Chat feels stuck | Saved replies refresh automatically about every four seconds while the page is visible. Queued messages can be cancelled; failed/cancelled messages offer an explicit paid retry. Reply allowances can be increased in conversation controls. There is no automatic retry or token streaming. |
| Drafts disappear while working | Reply refresh replaces only the transcript/proposal area. Unsent chat text is retained in this browser session, restored on reload and cleared after acknowledged sending or sign out. Proposal forms being edited are not replaced by background refresh. Avoid composing sensitive drafts on a shared browser account. |
| Employee status opens stale work | Refresh updates assignment titles, task links, project links and last-action labels together. Failed refresh is visible. Saved work still depends on a current worker heartbeat. |
| Scattered decisions | Reviews, Attention and the Overview decision count use one queue, including Team task approvals, new meeting intake, proposed memory and communications work proposals. Links to an owned execution lead back to its employee task. |
| Repetitive approvals | Conversation proposals let you review risk, sensitivity and acceptance criteria. Routine work is not automatically reclassified as restricted/consequential. Project minimums still apply. Public/Internal instructions require explicit confirmation that private conversation content has been removed. You may approve the exact task's start during this same review; this retains all budget, team, project, employee and tool gates. |
| Split task lists | All tasks has department, employee, status, priority, deadline and text filters. Employee and earlier execution records appear together, without duplicating an employee task's execution. |
| Employee chat selection is misleading | An employee selection filters the history to that employee and preselects that person for a new conversation. |
| History is difficult to find | Conversation title search and paging cover the full room list, including older rooms. Chat offers older-message navigation. Project conversation lists have paging. Explicit, versioned corrections can move or unlink a room's whole history within its department. Pending replies and unresolved proposals block moves until handled. |
| Inbox loses position | Review and local draft editing preserve account, search, state, page and selected message. A linked email account retains visibility of earlier unanalysed previews and local review state. Request analysis and edit saved reply drafts in the selected-message pane under existing consent controls. |
| Calendar is disconnected from daily work | Date navigation, meeting search, date-specific creation and PKT rescheduling are available. Planning deadlines appear in month cells and selected-range notices. Invitation review previews original and PKT times and possible confirmed-event overlaps before confirmation. Unknown durations remain uncertain. |
| Technical/readability friction | Department/employee labels replace IDs in normal assignment forms; task pages foreground the assignment and verified output, with less relevant controls in details. Chat and deliverables render escaped headings, bold text, lists and code blocks. No arbitrary model HTML executes. Current tabs and keyboard focus are clearer; narrow-screen views are improved. |
| Browser sign-in failure discovered during QA | Signed-out login pages no longer request protected app assets, preventing those requests from replacing the sign-in cookie and making the displayed form expire. |

## Boundaries retained

- Writing remains a department skill, not an eighth specialist.
- No external email, Slack or WhatsApp sending is introduced. Drafts remain local.
- No budgets, model rate cards, reading consent or team automation are enabled automatically by the upgrade.
- Calendar changes remain local; there is no Google Calendar synchronization, automatic invitation sending or automatic acceptance of ambiguous dates.
- Project chat proposals still require an explicit owner action. Checkbox approval applies only to that exact reviewed task and cannot weaken project controls or external-action/tool permissions.
- The board represents saved work and connectivity. It does not simulate eight simultaneous AI processes.
- Speech remains the v1.28 browser-based English/Urdu dictation feature. Real microphone recognition requires a compatible browser and permission; it is never auto-sent.
- Search is by conversation title and task/project fields; this release does not add semantic search across private conversation bodies.

## Live acceptance check

Use `ACCEPTANCE-CHECKLIST.md`. The included local/browser tests use synthetic data and mocked providers. They do not prove your live email credentials, model account or microphone recognition.

## Rollback to v1.28 code

The successful installer prints a code backup path such as `/home/superhuman/app/backups/v1.29-TIMESTAMP`. Replace the example path below with that exact printed path:

```powershell
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 "bash /home/superhuman/superhuman-v1.29-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.29-TIMESTAMP"
```

Rollback verifies installed and backup checksums before restoring. It retains your data, approved tasks, messages, meeting changes and room corrections. Pending Team Room replies are cancelled rather than replayed with older context behaviour. The worker remains paused for inspection. This is a code rollback, not a deletion of the data created while using v1.29. Review the retained work before resuming the worker.

## Optional checks on Ubuntu

From `/home/superhuman/app`, as the `superhuman` user:

```bash
/home/superhuman/app/.venv/bin/python /home/superhuman/superhuman-v1.29-upgrade/install_v129.py --preflight
/home/superhuman/app/.venv/bin/python /home/superhuman/superhuman-v1.29-upgrade/install_v129.py --check
```

The launcher already runs the required checks. No new server dependencies are needed. The headless browser used during local QA is not included in the upgrade and is not installed on your server.
