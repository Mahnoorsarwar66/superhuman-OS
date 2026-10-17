# Superhuman OS v1.33 — A simpler workspace

Requires installed v1.32. This is an interface-focused installation: a shared visual system, focused workspaces and clearer navigation over the existing execution/approval system. No new agent, model, permission or business-data schema is added.

## What changes

- One consistent font stack, 16px body text, restrained heading sizes, clearer spacing, quieter cards and buttons, and readable status labels. The green identity remains. Fonts use Inter when already available and otherwise the local system font; the app makes no external font request.
- A consistent sidebar with simple icons, a compact mobile menu, visible keyboard focus, a skip link and reduced-motion support. Coding remains directly accessible.
- Overview prioritises your decisions, current projects and briefing shortcuts. Worker controls and diagnostics are grouped in an expandable area.
- All projects appear in one list. Project type is a filter: All projects, With milestones, Task-based and Earlier work. The old milestone-project URL remains compatible with this unified list.
- Individual projects use Summary, Plan & work, Files & evidence, Conversations, Activity and Manage. Configuration is kept under Manage; original source grants, recipient consent and governance fields remain.
- Milestones separate Deliverable, Evidence, Reviews, History and Manage. Setup/start and PDF page-inspection controls are in Manage. Exact-version strategic approval and revision controls are in Reviews.
- Evidence separates Requirements & sources, Investigations and Review standards. Once scope is confirmed, its confirmation form becomes a saved status. Scope-change and audit tools remain available through an expandable section.
- Plain control labels such as Confirm requirements, Save evidence review, Download deliverable text and Reopen affected work. Submitted values, source quotations, user titles and report bodies are not rewritten.
- Department navigation consistently groups work/priorities, files/research, conversations, agent/supervision and activity. Agent pages retain actual saved assignments and existing live status refresh; no simulated work or continuous thinking is shown.
- Inbox gets cleaner spacing, collapsible account details on phones, message-list/detail anchors and a return-to-messages link. Calendar gets one compact date/view toolbar, optional search/date tools and a responsive seven-column month view. PKT conversions remain unchanged.
- Storage shows saved facts/source status before editing; metadata and source access controls sit under Manage source & access. Project filtering uses a named project selector. Settings groups people/context, connections, operations and advanced tools.
- HTML form/filter errors show a readable explanation and a way back. JSON clients retain their existing responses. Completed POSTs return to the selected matching project/milestone view when the browser supplies a same-site referrer.
- Routine milestone contribution reviews are no longer presented as additional owner decisions. The owner milestone gate appears once; exceptional recovery, source-change and approval items remain in the queue.

## Install from Windows PowerShell

Install v1.32 first. Extract this ZIP into `C:\superhuman-os-starter`, so the upgrade folder is directly inside it.

Run these commands separately in Windows PowerShell:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.33-upgrade" root@167.71.196.20:/home/superhuman/
```

```powershell
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 'chown -R superhuman:superhuman /home/superhuman/superhuman-v1.33-upgrade; bash /home/superhuman/superhuman-v1.33-upgrade/upgrade_server.sh'
```

The launcher checks exact source/dependency compatibility and service accounts, stops the services, makes a private data backup, tests a staged copy, installs guarded UI changes, checks local assets, restarts the services and captures the existing local baseline. Production CLI/orchestrator, credentials and service configuration are retained.

If source recognition fails, do not force the installation or edit the guard. Share the exact message so the installed variant can be inspected.

After installation, reload the browser. Use **Ctrl+F5** once if it still shows the previous page. New theme assets use a release-specific URL. Existing authentication and consent controls still apply.

## Where things moved

| Previous location/name | New location |
| --- | --- |
| Separate Milestone projects view | Projects > Project type: With milestones |
| Project activation and governance | Project > Manage |
| Shared project materials | Project > Files & evidence |
| Milestone start, criteria and guide page checks | Milestone > Manage |
| Current integrated result | Milestone > Deliverable |
| Strategic approval/revision | Milestone > Reviews |
| Requirement register | Milestone > Evidence > Requirements & sources |
| Research gaps | Milestone > Evidence > Investigations |
| Rubric | Milestone > Evidence > Review standards |
| Previous packet versions and decisions | Milestone > History |
| Department plans/priorities | Department > Work & priorities > Manage plan & priorities |
| Department employee/supervision | Department > Agent & supervision |
| Storage metadata and sharing | Source item > Manage source & access |
| Budget, connections, worker and diagnostics | Settings, grouped by purpose |

Existing bookmarked routes and POST actions remain. Managed project task creation is directed to its milestone work packages rather than a generic form that cannot create authorised linked work.

## What to check first

Open Overview, your endorsement project and M1. Check that the next action is understandable, the navigation labels are clear, and the information you need for a decision is visible without opening technical details. Then try Inbox, Calendar, Storage and the employee board on both your desktop and phone.

Use `ACCEPTANCE-CHECKLIST.md` for the full owner review. The package has not been installed on the live server, and local tests do not establish live provider access or substantive business-plan quality.

## Important boundaries

This release reorganises presentation. Source access, risk controls, budgets, worker scheduling, exact-version approvals, evidence freshness, independent reviews and change propagation continue to use the existing v1.32 backends. Collapsing a control does not bypass it. Quotation hashes and scorecards still do not prove factual correctness.

The interface works with server-rendered links/forms without JavaScript. JavaScript enhances mobile menus, browser-back controls, status wording and repeated-submit handling. Existing chat draft protection, dictation, refresh and calendar logic remain. Some older diagnostic/execution tools retain detailed records and specialised layouts within the shared shell. The review queue still exposes genuine recovery actions rather than hiding them for visual simplicity.

Project activity shows up to 100 matching entries from the latest 2,000 team events, with full execution logs available in tasks. Long outputs retain their existing bounded review/export rules. No external sending/submission, advanced deliverable generation, new chat front door or questionnaire is added.

## Check without installing

On Ubuntu, from `/home/superhuman/app`:

```bash
.venv/bin/python /home/superhuman/superhuman-v1.33-upgrade/install_v133.py --preflight
.venv/bin/python /home/superhuman/superhuman-v1.33-upgrade/install_v133.py --check
```

Preflight checks source/dependencies. Check runs offline tests in a staged copy without changing installed source or owner data. Neither makes real model requests or proves live API connectivity.

## Rollback

Use the exact code-backup directory printed during installation:

```bash
bash /home/superhuman/superhuman-v1.33-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.33-TIMESTAMP
```

Rollback refuses modified installed source or extra package files. It restores exact v1.32 source and removes the new interface package. Business records, evidence, approvals, permissions, budgets, sources and export history remain. The worker is left paused for inspection; coordination settings and task permissions are not reset by this UI rollback. Roll back v1.33 before using an older release's rollback script.
