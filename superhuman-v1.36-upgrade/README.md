# Superhuman OS v1.36 — Team workspace and coordinated conversations

Requires the installed v1.35 application. This is an upgrade package, not a replacement application. The installer recognises the exact integration files and stops before overwriting unknown versions. Customized production `superhuman/cli.py` and `superhuman/core/orchestrator.py` are not modified.

## What changes

- Team opens a balanced workspace: compact eight-person overview, primary direct conversations, project channels, employee workloads, attention and recorded activity.
- Direct-message reply threads retain a link to the exact original message and the same employee/project context. Their controls also survive live transcript refresh.
- One stable primary direct conversation per employee reuses the most recent eligible existing conversation. It is created/selected only when you click that employee. Older histories remain available.
- Project channels contain genuine shared threads. A directed question queues one employee. A team question starts with the project lead, who may request up to two approved specialists and then synthesize their actual saved replies: at most four reply attempts per message. The Twin retains supervision; the department lead retains project leadership.
- Shared replies use only approved project participants. Storage retrieval for a public-to-the-project reply excludes documents not approved for every participant. Sharing revocation, employee pause, changed context or changed linked documents stop stale replies.
- Conversation title and message-content search, employee/project/date filters, exact message anchors, pagination, pins, archives, saved read markers and literal `@Mahnoor` / `@owner` mentions. Dates in the search filter are explicitly labeled saved UTC dates; displayed timestamps use existing PKT formatting.
- Historical replies receive a migration baseline, rather than invented unread counts. Opening a page does not silently mark messages read. Use Mark read / Mark current replies read for the exact visible state.
- Employee profiles show role, actual workload, review waits, worker availability and management links. Larger existing fictional AI portraits remain unchanged, without the old bot overlay.
- Working context shows confirmed notes, project/milestone links, exact-version document links and recorded context for the latest reply. Document excerpts and recent chat history are bounded; a saved synthesis is not automatically a confirmed fact.
- Uploads go to the existing Storage department, tagged to the conversation's project as confidential-or-higher drafts. Review/approve the Storage source and named recipients, then link its exact current version. Source files are never overwritten. Supported formats and the 10 MB limit are unchanged.
- Work cards retain outcome/instructions, owner, acceptance criteria, due date, risk, sensitivity and milestone. The owner may authorize the exact card, or request an independent Twin review for routine work. The Twin cannot approve its own proposal. Each card has at most two Twin review attempts.
- Channel settings offer an explicit opt-in for automatic Twin review of routine internal suggestions. It is initially off. Strategic, consequential or restricted work remains for the owner. A changed project or card invalidates a stale decision. A managed project card must enter an existing working milestone, preserving the lead, specialist, Twin and owner review sequence.
- Actual project assignments, handoffs, milestone review findings and saved decisions are available inside the channel. They are labeled work records; internal reasoning and invented employee conversations are not shown.

## What is retained

Existing chats, projects, milestones, accepted packets, interviews, memory, permissions, rate cards, dollar budgets, credentials, service definitions and external-action boundaries. Channel replies and review calls use the existing shared worker and metered model client. No new provider, external sending tool or increased monthly budget is enabled.

Read markers and conversation organization are owner-account settings: this remains a single-owner application, not a multi-user Slack service. Mention attention recognizes explicit saved `@Mahnoor` and `@owner` text; it does not provide email, push or external Slack notifications. Channels are project-scoped rather than arbitrary cross-department rooms. Conversations with external people are outside this release.

## Install from Windows PowerShell

Extract the ZIP so this file exists:

`C:\superhuman-os-starter\superhuman-v1.36-upgrade\upgrade_server.sh`

Run in Windows PowerShell:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.36-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

Only after the prompt changes to `root@ubuntu...`, run on Ubuntu:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.36-upgrade
bash /home/superhuman/superhuman-v1.36-upgrade/upgrade_server.sh
```

The server script preflights the source, stops the existing services, creates a private backup, checks the staged upgrade using synthetic data without provider calls, installs it, initializes additive Team tables, and restarts the services. The full regression check is lengthy, especially on a one-CPU server, and the services remain stopped during installation. Keep the SSH session open until the script reports success. Stop and share an error if one appears; do not bypass the source guard or run an older upgrade on this version.

Then open https://superhuman.167-71-196-20.sslip.io/team-hub and refresh with Ctrl+Shift+R.

## First use

1. Open Team, choose an employee, and verify their existing direct conversation and controls.
2. For a project channel, use an existing project with department leadership and approved team-sharing. Create a channel and confirm its approved members. Nothing is automatically copied from private direct chats into the channel.
3. Create a thread, optionally associated with a milestone. Activate the existing project before requesting replies. A directed question is the lowest-cost first check.
4. Ask a team question. Confirm that actual named contributions appear, followed by the lead's synthesis. The channel has an initial lifetime allowance of 40 attempts, adjustable in its controls; existing dollar limits also apply.
5. Inspect a work card. Keep automatic routine review off until you have reviewed the proposed scope and observed a successful manual Twin review. The checkbox is then available per channel.
6. Existing milestone plans are retained. This release does not generate a milestone plan automatically for a new project; use the existing manual plan or endorsement blueprint.

## Rollback

The installer prints an exact backup directory. On Ubuntu, substitute that path:

```bash
bash /home/superhuman/superhuman-v1.36-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.36-TIMESTAMP
```

Rollback verifies installed and backup hashes, pauses the worker, cancels pending new channel/review calls before their context guards are removed, restores exact v1.35 integration code, and retains business data, files and new Team records. It does not delete accepted outputs or restore an old database over your new work. Inspect the saved state before explicitly resuming the worker. Extra owner-added package files or changed source cause rollback to refuse rather than delete them.

## Verification limits

See VALIDATION.md. Automated checks use synthetic data and mocked providers. This package has not been installed on the live server. Real-browser desktop/mobile visual verification and microphone-service verification were unavailable in this environment; check the actual screens after installing. No model quality, visa success or independent strategic judgment is guaranteed by passing software tests.
