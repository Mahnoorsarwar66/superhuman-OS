# Superhuman OS v1.32 — Evidence, Quality & Follow-through

Installation 2 of 2. Requires the exact v1.31 installation. This package extends the existing Projects and Milestones workspace; it does not add another navigation console or another task engine.

## What changes

- Each milestone gains a versioned requirement register, critical/supporting labels, source origins, quotations, evidence judgments and a review history.
- Evidence is either an exact quotation from a current approved Storage source or from an accepted milestone task. The lead and The Twin must have source access. A URL or an agent's unsupported assertion is not enough. Task outputs are secondary research/deliverables, not automatically primary-source verification.
- PDF evidence uses an explicit `page:N` locator, including later pages outside the ordinary 40,000-character file excerpt. This is text extraction only; OCR and visual interpretation are not added.
- Specialists can propose requirements, evidence, research gaps and initiatives through scoped employee tools. Only the lead or owner can accept/reject/contest evidence. Only you confirm the requirement scope and apply strategic changes.
- The existing worker turns eligible research gaps into deduplicated assignments for approved milestone specialists. Integration waits for critical investigations and approved task dependencies. The lead reviews the actual result before an investigation is resolved. Existing risk, privacy, tool, request, task and budget limits remain.
- Reviewers use an explicit quality rubric: evidence, context, completeness, coherence and usefulness, with department-specific context standards. You can refine the standards. Critiques have scorecards tied to the exact packet and register version. A valid critique may report failure; The Twin can then request integration revision. Acceptance requires passing current specialist and Twin scorecards.
- Packets pin the requirement/evidence/rubric state. New evidence or scope changes after packet assembly require fresh review. Changed, expired or revoked accepted sources raise an impact record and block the affected milestone and its dependency descendants.
- You can apply an impact decision to reopen affected accepted work. Prior packets, decisions and action history remain; approval is withdrawn and fresh scope confirmation/review is required. Request/action ceilings and spending are not reset or increased.
- Initiative proposals connect to existing governed projects and can link an existing project signal or conversation suggestion. Approved initiatives can have numeric baselines, targets, review dates and source-backed observations. Outcome follow-ups appear in the existing Attention queue. Recorded change does not establish causation or ROI.

Katherine remains the endorsement project's lead. The agreed seven milestone teams, The Twin's supervisory role, specialist independence and your strategic approval remain in force. No external sending/submission permission is added.

## Install from Windows PowerShell

Install v1.31 first. Extract the ZIP into `C:\superhuman-os-starter`, producing `superhuman-v1.32-upgrade` directly inside that folder.

Run these commands separately in Windows PowerShell:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.32-upgrade" root@167.71.196.20:/home/superhuman/
```

```powershell
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20 'chown -R superhuman:superhuman /home/superhuman/superhuman-v1.32-upgrade; bash /home/superhuman/superhuman-v1.32-upgrade/upgrade_server.sh'
```

The Ubuntu launcher checks service accounts and exact source/dependency compatibility, stops both services, makes a private data backup, tests a staged copy, installs guarded source changes, sets up the schema/internal tools, restarts services and captures the local system baseline. Production CLI/orchestrator, credentials and service configuration are retained.

A mismatch stops the upgrade. Do not force it or edit hashes. Share the exact message for inspection of your installed variant.

## Where to work

1. Open Projects > Milestone projects > your project. Each milestone has a visible **Evidence & quality** link.
2. Let the assigned specialists propose requirements from the actual guide and project evidence. You can also add/edit them. Criteria and registers remain provisional until you review the real scope; the guide has not been reviewed by this installation.
3. Link exact source evidence. For Storage sources, approve the source and the lead/Twin access first. A proposed quotation is not an accepted fact. The lead can judge it within existing authority; contested critical evidence blocks acceptance.
4. Confirm the requirement register scope. This is a scope decision, not a request to approve every routine research action. Requirements/rubric changes invalidate the confirmation. Evidence judgments and investigation completion do not require repeated scope confirmation by themselves.
5. Record gaps before integration completes. While the project/milestone is active and budget is ready, the worker assigns eligible investigations using existing employee tasks. You may defer an unassigned supporting gap with a reason; a critical gap must be investigated. A held investigation is shown for owner inspection/retry.
6. Review scorecards and The Twin's revised/accepted packet, then give strategic approval on its exact version as before.
7. Inspect **Changes needing your decision** on the project page. Applying the change reopens affected work, retains packet history and resets scope/criteria confirmation. Active execution must finish or be paused first. Recheck task tools and remaining budget/request ceilings before continuing.
8. Open **Initiatives & outcome review** from the project. Approve a proposal, define its baseline/target/unit/review date, then add an exact source-backed observation and review the measurement method. The system reports the change and whether the target is reached; it does not claim causal impact.

Private requirements/evidence are filtered from lower-classified task contexts. If a register becomes more private than the existing integration assignment, packet submission is held until you raise the task controls and inspect public-web permissions. Adding private sources never grants broader research or sharing authority.

## Existing work and migration

- Existing v1.31 approved milestones stay approved as historical decisions and are explicitly labelled as not retrospectively verified against this new register. New gates apply to new packets. Changes to registered accepted evidence still propagate normally.
- Existing in-review packets are held for owner impact inspection so they cannot bypass the new evidence/quality gates. Apply the change, build the register and resubmit.
- Project activation, employee pauses, source grants, routine authority, budgets and the paused endorsement blueprint are preserved. Setup does not create research tasks, call a model or start M1.
- Existing employees with milestone reading/collaboration tools receive the corresponding internal register tools once. Later owner revocations are respected. Re-running setup is idempotent.

## Limits and remaining work

A quotation match, source hash or a model's passing score is not proof that the source is true or that the endorsement case is strong. Domain judgment and your strategic review remain essential. Forecasts must not be labelled actual observations. Review the measurement method: a quoted number alone does not establish how it was calculated.

No live model/provider, guide, research or business-outcome validation was performed in packaging. Automated tests use synthetic data and mocked providers. Current outputs retain v1.31 basic PDF/Word export formatting; advanced financial models, OCR, external execution, questionnaires and a unified Twin front door are outside this release. The new outcome records are a foundation for actual measured operation, not a claim that the broader business-impact gap is closed.

Limits are bounded: 80 requirements/milestone, 12 evidence entries/requirement, 24 gap records/milestone, existing 12 current assignment slots and 240 project tasks, and a bounded full review context. Oversized contexts are held for work splitting. No silently truncated review can approve a packet. Investigation requests and all coordination remain within existing worker/employee budgets. Your monthly budget is not changed.

## Check without installing

On Ubuntu, from `/home/superhuman/app`:

```bash
.venv/bin/python /home/superhuman/superhuman-v1.32-upgrade/install_v132.py --preflight
.venv/bin/python /home/superhuman/superhuman-v1.32-upgrade/install_v132.py --check
```

Preflight checks source/dependencies only. Check runs offline tests on a staged copy without changing installed source or owner data. Neither proves live model connectivity.

## Rollback

Use the exact code-backup directory printed by the installer:

```bash
bash /home/superhuman/superhuman-v1.32-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.32-TIMESTAMP
```

Rollback refuses edited installed source or extra package files. It restores exact v1.31 code, retains requirements/evidence/gaps/scorecards/changes/initiatives/measurements and all existing project data, removes unsupported v1.32 tool names, disables milestone coordination and leaves the worker/affected work paused. v1.31 does not enforce v1.32 registers: inspect that limitation before explicitly resuming older code.

On reinstall, removed employee tools return only when there has been no intervening owner edit to their permissions. Run-level tool permissions and paused work require inspection. Roll back v1.32 before using the v1.31 rollback script.
