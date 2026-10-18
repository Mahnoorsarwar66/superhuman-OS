# Superhuman OS — workspace and implementation baseline

The local `superhuman/` tree was consolidated from the complete v1.41 server source on 18 October 2026. `source-provenance.json` preserves that 239-file baseline. The working tree now includes the local WF02 objective implementation described below, so it intentionally differs from those historical hashes. Incremental upgrade packages remain release history. Implement new behavior in this source tree and record acceptance evidence in [the workforce roadmap](AGENTIC_WORKFORCE_ROADMAP.md).

The server checkout's version markers report 1.41.0 and match all 17 latest package files. Both services were active under `superhuman` with `/home/superhuman/app` as their working directory. The checkout has no Git history; its captured source fingerprint establishes the baseline. This inventory does not attest to source already loaded in a running process.

The conversation path supports bounded public-web research and local drafting, with governed assignments and results returned to the source conversation. The local candidate adds explicit objective identity, shared execution limits, owner-reviewed changes to ordinary assignments, and independent deliverable review. Autonomous graph replanning, broader conversation planning, milestone migration, recovery, and broader evidence assurance remain roadmap work. This candidate has not been deployed; live provider compatibility and real multi-specialist competence remain unverified.

## Bounded objectives in the local candidate

Open an unstarted ordinary task and expand **Track this assignment as an objective**. Set total dollars, model-request attempts, elapsed wall time, revision rounds, and an authorization note. The objective keeps that assignment's brief and criteria; a conversation-created assignment also retains its exact owner request, turn, and source conversation. Other requests in the same conversation are independent. Existing task, employee, project, source, model, and global budget controls still apply.

The resulting objective page links all assignments and shows charged/reserved dollars, request attempts, revisions, deadline, current brief, and plan history. Add further assignments there; real handoffs inherit the parent's objective automatically. Objective-scoped Twin decisions, specialist execution, draft subrequests, and automatic reviews use the same existing cost ledger. Assignments and provider requests run sequentially within each objective. No new scheduler or paid provider was introduced.

Pause, resume, restart, handoffs, task-limit changes, and allowance amendments preserve accumulated consumption. Wall time runs from creation, including paused time. Unknown paid outcomes keep their full dollar reservation until explicit reconciliation. Pre-provider local refusals release dollars only, retaining the recorded request attempt. Provider overruns retain their actual charges and block further work rather than changing historical accounting. In-flight calls may finish and be billed; current controls are checked again before the next provider invocation or tool action.

An owner may amend total allowances with a recorded reason. Formal output-revision requests and brief changes share the revision allowance; zero revisions permits an initial attempt but no revision round. Plan changes retain earlier versions. Changes to started work require the explicit impact workflow below. Milestone enrollment, asynchronous inbox jobs, and tool histories without a reviewed replay adapter remain refused. An existing specialist-alternative route cannot bypass those restrictions.

For an enrolled conversation assignment, open its original work message and expand **Revise this objective before execution**. Submit the complete replacement brief, success criteria, and impact/reason. The owner control saves a new plan and feedback/status in the same conversation, consumes one revision round, and requires start approval again. Execution follows that plan while the original request, spending, reservations, deadline, and total allowances remain intact. Duplicate submissions return the saved receipt; stale versions, changed room scope, archived conversations, started work, and unsafe scope changes are refused. Plain-text objective revision requests link to this control rather than creating another assignment. This pre-execution control does not change started work or choose an objective from ambiguous language; use the separate impact workflow below.

For started work, pause the objective, let current operations settle, and reconcile uncertain spending. Open **Review changes to started work** on its objective page (also linked from the original conversation). Enter the replacement objective brief/criteria and an assignment-by-assignment impact decision. Changed assignments and their dependent/handoff-context work must be revised; retain only accepted completed work whose original brief and criteria remain valid, with a recorded reason. Review the prepared assessment and historical outputs before choosing **Apply reviewed plan change**. The assessment becomes stale if work, accounting, or relevant authority changes before application.

Application uses one objective revision, saves the prior state, invalidates affected output/start approvals, and leaves the objective paused. Approve each changed assignment through its existing **Approve start / continuation** control with an inspection note, then explicitly resume the objective. The same task and run IDs, spent requests, action counts, cost ledger, limits, and deadline continue. Earlier raw actions and artifact bytes remain in history, but cannot supply current evidence, permission, or cache hits. Reached task limits require separate explicit amendments through existing controls. Current affected-history support covers calculation, bounded research/local drafting, and resolved internal handoffs/challenges; milestones, cross-objective effects, consequential authority changes, and unsupported tool replay are held for their own adapters. No new scheduler or provider was introduced.

For an enrolled task awaiting output review, use **Independent deliverable review** on its task page. Select a specialist who did not author the deliverable and enter one rubric criterion per line. Existing employee records need an explicit `workforce.review_source` tool grant through that employee's permissions first; initialization does not expand existing grants. Start the new reviewer assignment through the normal controls. Its separate run reads the complete bounded artifact, brief, criteria, rubric and saved execution evidence, then produces a structured assessment. Inspect and accept the critique to record its findings. This records the review and does not accept the author's output.

Once assigned, independent review stays mandatory across output revisions. Every current reviewer must pass before **Approve output** can succeed. Supported findings include an exact passage, severity, problem and requested correction. **Request revision** applies those findings, consumes one shared objective revision, and holds the same author task/run for fresh **Approve start / continuation**. Old artifacts, reviews and accounting remain historical; the replacement deliverable needs a new reviewer assignment and run. Review work shares the objective's cumulative spending, request and time limits. Owner approval is required for governed output and critique decisions. Unsupported tool replay, already-started consumers, and broader impact replanning after review assignment remain blocked. Review assesses the supplied evidence; it does not automatically retrieve or establish the truth of external sources.

Accepted tasks do not automatically complete an objective. **Accept completed objective** requires every member assignment to have passed its existing output review, current artifact/evidence and mandatory independent review checks to pass, accounting to be resolved, open handoffs/disagreements to be resolved, and an owner statement that the recorded criteria are satisfied. This does not assert that a business outcome has been measured or that factual accuracy has been independently established.

The final WF02 candidate passed **565 existing regressions and 31 new objective integration tests** on Linux/Python 3.12.3, plus **47 overlapping local checks** on Windows/Python 3.13.0. Providers were fixtures and external networking was blocked. The roadmap's UP003/E003 entries record the exact tested source fingerprint and retained logs; this is implementation evidence, not production or live-model acceptance.

Enrollment is explicit and limited to unstarted root assignments without prior spending or handoffs. Existing work is not silently reclassified. The four additive `workforce_objective_*` / `workforce_objectives` tables store identity, membership, plans, and links to canonical costs; existing project/task/cost records remain authoritative. Repeated initialization preserves legacy permissions, spending, and history. Baseline source-restore tooling intentionally refuses to overwrite these new working-tree edits. Before any older-code rollback, stop/pause the worker and pause objective-managed assignments with the current controls; retain all objective/accounting tables and do not resume those assignments under code that ignores their limits. A reviewed release/rollback package remains WF01 work.

Started-work changes add `workforce_plan_changes` and `workforce_task_plan_controls` for immutable impact snapshots, application receipts, approval gates, and prior-action boundaries. Independent review adds `workforce_review_policies` and `workforce_reviews` for immutable rubric/artifact/evidence snapshots, separate reviewer identities, findings and revision dispositions. Initialization is additive and repeatable. Keep these records with the existing ledger and artifacts during backup/restore. Older code ignores the new approval/evidence boundaries, so revised and review-governed assignments must remain quarantined during any older-code rollback until a reviewed recovery procedure is available.

## Install and verify

For a fresh checkout, use Python 3.12 (the Linux baseline) and the pinned dependency specification:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip check
```

`requirements-server-v141.lock` records exact observed server package versions, plus Windows timezone and console dependencies discovered during validation. It is a version lock, without wheel hashes. This session retained the original `.venv` and used `.workforce/venv` as its isolated validated environment; the original environment still has OpenAI and ReportLab versions outside the historical server specification. Existing `.env` values and local business data were retained. `.env.example` provides optional model configuration fields; offline checks need no key.

For an empty local data directory, configure a local owner account and start the web interface:

```powershell
.venv\Scripts\python.exe -m superhuman.hosted.cli setup --origin http://127.0.0.1:8000 --tunnel
.venv\Scripts\python.exe -m uvicorn superhuman.hosted.web:app --host 127.0.0.1 --port 8000
```

Worker activation, model rates, authority, and budgets use the application's existing controls. No worker was started and no production deployment was performed during consolidation.

Use the read-only baseline checker before changing application source. It does not import the application, load `.env`, initialize databases, or call providers:

```powershell
.venv\Scripts\python.exe tools\workforce_baseline.py
# Optional: include schema fingerprints and user_version, without reading business rows.
.venv\Scripts\python.exe tools\workforce_baseline.py --include-schema
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run it from the checkout, using the intended Python environment. `--root PATH` can inspect another local checkout. Reports include source hashes, Python syntax results, installed dependency versions, declared requirements, and exact payload checks for packages with `FILES.json`. The Git commit identifies the checkout base; the source fingerprint also captures uncommitted application changes. These checks do not establish a runnable integrated release or validate model quality.

The initial local inventory found 15 of 17 v1.41 manifest paths missing and two different from the payload. Consolidation resolved that source mismatch, including the packaged organisation seed and eight portrait assets. Prior local source is retained in `.workforce/local-before-v141`; generated host reports and private backups are ignored by Git.

Validation of the captured complete application: **565 Python regressions passed** on Linux/Python 3.12.3 with fixture providers and external network access blocked; **one JavaScript live-refresh test passed**; **16 tooling tests passed** locally. A synthetic legacy-project migration, repeated initialization, and old-code readback preserved records and artifact bytes. Those checks do not establish recovery of real spending/permission histories, power-loss durability, or live provider quality.

Run the offline application suite against an explicit source tree, with isolated temporary data and credentials excluded:

```powershell
.venv\Scripts\python.exe tools\run_workforce_checks.py --source . --log .workforce\checks.log
node superhuman-v1.41-upgrade\tests\workspace_live.test.cjs superhuman\workspace\assets\workspace.js
```

The roadmap specifies sequential initial workforce execution and a gate before adding parallel dispatch. The local candidate enforces cumulative limits for explicitly enrolled ordinary assignments and supports explicit independent deliverable review. Broader work-graph migration/replanning, owner-approved live evaluation thresholds, and production release acceptance remain open.

## Source consolidation and restore

`tools/capture_workforce_source.py` downloads only inventoried application files into a new staging directory and verifies every hash before writing. `tools/consolidate_workforce_source.py` backs up existing source, refuses unreviewed local drift, and preserves data and configuration. Its `--restore` mode accepts the recorded backup only while consolidated source and provenance remain unchanged; it refuses to overwrite subsequent edits. Source restore is separate from database rollback and must not be treated as permission to run older code against arbitrary newer business state.

## Historical starter instructions

The instructions below describe the original starter CLI only. For incremental server releases, use the matching package instructions only after verifying its required predecessor source.

A local-first, approval-first foundation for a personal AI workforce.

## What works now
- Local SQLite task register (seven workstreams, shared writing specialist)
- Create, list and inspect tasks using a command-line interface
- Ask Superhuman Core to produce a research/draft plan (requires your OpenAI API key)
- Store execution output locally; **no email, payments, external publishing or external app actions**
- Every generated answer is marked as a draft pending human review

## Requirements
Python 3.10+ and an OpenAI API key to use the AI command (task management works without a key).

## Install
```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # on Windows copy .env.example .env
```
Edit `.env` and set `OPENAI_API_KEY` to your personal API key. **Never share that key in chat or commit it to git.**

## Run
```bash
python -m superhuman.cli init
python -m superhuman.cli add --project endorsement --title "Develop UK endorsement business plan outline" --details "Structure and evidence checklist"
python -m superhuman.cli list
python -m superhuman.cli run 1
python -m superhuman.cli show 1
```

`run` makes an AI request, writes the draft to `data/outputs/`, and changes task state to `needs_review`. No external actions are performed.

## Next engineering milestones
1. Document ingestion with explicit consent and per-project access control
2. Evidence-backed research agent with source citations and verification
3. User authentication, encrypted secrets vault, approval queue and audit log
4. Background task workers, retries, budgets and monitoring
5. Specialized integrations (email, calendar, files, repositories) with least privilege
6. Writing DNA evaluation suite and controlled agent quality testing

This is a **starter**, not a production-secure autonomous application. Do not upload confidential third-party or client data yet.
