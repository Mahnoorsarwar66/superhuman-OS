# Superhuman OS v1.31 — Project Leadership & Milestones (installation 1 of 2)

Requires installed v1.30. This release adds the agreed project-led milestone workflow over existing projects, tasks, agents and Storage. It does not build the business plan itself or claim to have reviewed the guide or audited the live server.

## Your endorsement project

The installer prepares one paused project with Katherine as lead, The Twin as supervisor and Mahnoor as strategic approver. Acceptance criteria remain provisional until the guide has been reviewed and you confirm/refine them.

| Milestone | Working team | Integration and review |
| --- | --- | --- |
| M1 Brief and evidence baseline | Katherine | Katherine integrates; The Twin reviews; Mahnoor approves |
| M2 Customer problem and initial market | Sarah | Katherine integrates; The Twin reviews; Mahnoor approves |
| M3 Innovation proposition | Katherine, James, Amelia | Katherine integrates; The Twin reviews; Mahnoor approves |
| M4 Commercial and delivery viability | The Twin, Katherine, James | Katherine integrates; Sarah provides an independent specialist review; The Twin reviews with her author contribution disclosed; Mahnoor approves |
| M5 Growth and financial case | Katherine, Chris | Katherine integrates; The Twin reviews; Mahnoor approves |
| M6 Integrated case and challenge | Katherine | Targeted reviews from Sarah, James, Amelia, Chris and Sam; The Twin reviews; Mahnoor approves |
| M7 Final package | Katherine | The Twin checks readiness; Mahnoor approves. Submission is a separate action. |

Katherine remains the lead even when another specialist authors the main investigation. The Twin contribution to M4 is saved separately and cannot substitute for independent specialist review.

## Included

- Project leads, working teams, independent reviewers and an explicit supervisor/owner hierarchy.
- Milestone questions, acceptance criteria, dependencies, provisional/confirmed status, assignment lists, blockers, versioned packets and decision history.
- Contributor assignments run through the existing bounded agentic engine. Katherine reviews their actual verified results; the integration assignment depends on accepted contributions. The Twin reviews the integrated packet; only the owner can approve the strategic milestone and release its successors.
- At least two automatic revision attempts after the initial submission. A third submission can be accepted; persistent problems escalate rather than looping indefinitely. Owner-requested revisions remain explicit decisions.
- Named, project-scoped grants to approved Storage versions. Existing Storage sensitivity, source freshness and conflict checks remain. Briefs and outputs require a separate explicit project sharing consent.
- Full contribution reading, versioned working notes and page-bounded PDF text extraction. M1 cannot be submitted with missing guide coverage. Blank/image-only pages can be personally inspected by the owner and recorded separately; that is not machine extraction or OCR.
- Exact consolidated packet snapshots with source hashes and PDF/Word exports using the existing basic exporter. Prior packets remain available as history.
- Project-scoped conversations for approved cross-department participants. Private global inbox context is not attached to project conversations.
- Existing Projects routes connect to the milestone workspace. Pending owner milestone decisions also appear in the existing review queue. Managed project work is excluded from the older generic Twin planning/review path so the lead workflow cannot be bypassed.
- Existing budgets, permissions, employee pauses, tool restrictions and worker scheduling remain in force. No new external-action permissions or always-running model loops.

## Install from Windows PowerShell

Install v1.30 first if it is not already installed. Extract this archive into `C:\superhuman-os-starter`.

Run these two commands separately in Windows PowerShell:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.31-upgrade" root@167.71.196.20:/home/superhuman/
```

```powershell
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 'chown -R superhuman:superhuman /home/superhuman/superhuman-v1.31-upgrade; bash /home/superhuman/superhuman-v1.31-upgrade/upgrade_server.sh'
```

The launcher validates exact source/dependency compatibility, stops both services, creates a private backup, runs the offline staged tests, installs guarded source changes, prepares the paused blueprint before starting the worker, restarts services and captures a local baseline. It does not overwrite the production CLI or orchestrator. Existing credentials, data and budget configuration remain.

Do not force a source mismatch. Share its exact message so the actual installed variant can be inspected.

## Start M1

1. In Storage, upload the actual guide to UK Innovator Founder, register its source and approve the current version. Upload/registration alone is not approval or proof of reading.
2. Open Projects > Project leadership & milestones > the EdSync endorsement project.
3. Under Shared project materials, link the guide with purpose **Required endorsement guide (PDF)** and approve named access for Katherine and The Twin. Link other EdSync materials individually; do not bulk-share private documents without reviewing their recipients.
4. Review the roster and project-output sharing consent. Enable milestone coordination and set the project status to Active. Existing Team activation, worker state and budget must separately permit execution.
5. Open M1. Review its provisional criteria and start the milestone. Confirm the criteria before the final Twin acceptance gate. Katherine can propose refinements for later, still-planned milestones after reviewing the guide.
6. M1 creates a public-research assignment and a separate guide/integration assignment for Katherine. Private guide material is excluded from public-web tool use. Guide integration has up to 48 model requests/40 decision steps; other initial assignments have 12 requests/16 steps. Each retains the existing $5 task ceiling and overall budget gate. Limits are ceilings, not promised expenditure or sufficient allowance for every model.
7. Review the polished packet after The Twin's review. Your approval applies to its exact version. Then start the next milestone when ready.

## Delegated authority and controls

Routine internal work can proceed within the approved project roster and existing gates. Katherine cannot add new participants, grant source access, change project governance, approve strategic milestones, override The Twin or perform external actions. Additional work packages can be added through the milestone workspace for its approved specialists. Existing open legacy tasks must be organised before attaching milestone leadership to their project.

Milestone review is separate from task completion. Direct task/canonical approval routes cannot approve managed milestone assignments outside this workflow. A packet cannot advance without accepted contributions, the required independent reviews, confirmed criteria and the appropriate owner gate. A paused project or revoked output-sharing consent blocks execution.

The worker uses metered, structured decisions for the lead and The Twin, with a maximum 20 milestone decisions per rolling hour across projects and no repeated calls for unchanged waiting state. Interrupted decisions are held for inspection; they are not automatically replayed. Project-related proactive signals are retained for the lead workflow/owner, rather than being planned by the generic coordinator.

## Material limitations

- Research, recommendations and projected inputs still need substantive review. Source hashes and execution evidence do not prove factual correctness, market validation or endorsement readiness.
- PDF reading is text extraction only, one to five pages at a time, with bounded output. Empty or truncated pages do not count as complete machine extraction. Retry smaller ranges; personally review image-only material or supply a readable version. Owner-inspected pages are identified separately. Working notes are reference data, not confirmed facts or proof of comprehension.
- Full source-output reading and automated reviews are bounded. Oversized results are held with an explicit instruction to split the work rather than silently approving a partial result. Long projects should use section deliverables. The existing agentic action history is bounded; working notes retain section findings.
- PDF/Word exports retain the existing basic text/heading formatting. This release does not add advanced layout, OCR, native presentation generation or formula-rich financial modelling. Export failures remain visible and cannot be treated as successful delivery.
- Later milestones do not automatically start after owner approval; the owner explicitly starts the next stage. Approval of M7 does not send or submit anything, and the overall project is not silently marked complete.
- Requirement/evidence registers, formal gap investigations, downstream reopening/impact propagation, wider initiative and impact measurement belong to installation 2. The broader Twin front-door and business-outcome gaps remain recorded as deferred. Questionnaires and external-action execution remain outside this release.

## Check without installing

On Ubuntu, from `/home/superhuman/app`:

```bash
.venv/bin/python /home/superhuman/superhuman-v1.31-upgrade/install_v131.py --preflight
.venv/bin/python /home/superhuman/superhuman-v1.31-upgrade/install_v131.py --check
```

Preflight performs source/dependency checks only. Check stages the release and runs offline tests without changing installed source or owner data. Tests use local synthetic records and mocked model/provider responses; they do not verify live API access or perform endorsement research.

## Rollback

Use the exact backup directory printed during installation:

```bash
bash /home/superhuman/superhuman-v1.31-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.31-TIMESTAMP
```

Rollback refuses changed installed source or extra package files. It restores v1.30 code and removes this package, while retaining milestone records, sources, packets, exports, notes and decisions. It disables milestone coordination and leaves the worker and affected runs/assignments paused. New tool names are removed from v1.30 execution permissions to avoid unsupported-tool failures.

Reinstalling v1.31 restores the removed employee tool permissions only if no later owner edit changed those permissions; work remains paused for explicit inspection/resumption. Affected run-level permissions should also be reviewed before resuming. Roll back v1.31 before using an older release's rollback script.
