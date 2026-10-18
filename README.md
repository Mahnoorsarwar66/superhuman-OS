# Superhuman OS — workspace and implementation baseline

The local `superhuman/` tree was consolidated from the complete v1.41 server source on 18 October 2026. `source-provenance.json` preserves that 239-file baseline. The working tree now includes the local WF02 objective implementation described below, so it intentionally differs from those historical hashes. Incremental upgrade packages remain release history. Implement new behavior in this source tree and record acceptance evidence in [the workforce roadmap](AGENTIC_WORKFORCE_ROADMAP.md).

The server checkout's version markers report 1.41.0 and match all 17 latest package files. Both services were active under `superhuman` with `/home/superhuman/app` as their working directory. The checkout has no Git history; its captured source fingerprint establishes the baseline. This inventory does not attest to source already loaded in a running process.

The conversation path supports bounded public-web research and local drafting, with governed assignments and results returned to the source conversation. The local candidate adds explicit objective identity and shared execution limits over ordinary team assignments. Broader conversation planning, active-work replanning, milestone migration, recovery, and independent quality review remain roadmap work. This candidate has not been deployed; live provider compatibility and real multi-specialist competence remain unverified.

## Bounded objectives in the local candidate

Open an unstarted ordinary task and expand **Track this assignment as an objective**. Set total dollars, model-request attempts, elapsed wall time, revision rounds, and an authorization note. The objective keeps that assignment's brief and criteria; a conversation-created assignment also retains its exact owner request, turn, and source conversation. Other requests in the same conversation are independent. Existing task, employee, project, source, model, and global budget controls still apply.

The resulting objective page links all assignments and shows charged/reserved dollars, request attempts, revisions, deadline, current brief, and plan history. Add further assignments there; real handoffs inherit the parent's objective automatically. Objective-scoped Twin decisions, specialist execution, draft subrequests, and automatic reviews use the same existing cost ledger. Assignments and provider requests run sequentially within each objective. No new scheduler or paid provider was introduced.

Pause, resume, restart, handoffs, task-limit changes, and allowance amendments preserve accumulated consumption. Wall time runs from creation, including paused time. Unknown paid outcomes keep their full dollar reservation until explicit reconciliation. Pre-provider local refusals release dollars only, retaining the recorded request attempt. Provider overruns retain their actual charges and block further work rather than changing historical accounting. In-flight calls may finish and be billed; current controls are checked again before the next provider invocation or tool action.

An owner may amend total allowances with a recorded reason. Formal output-revision requests and pre-execution brief changes share the revision allowance; zero revisions permits an initial attempt but no revision round. Plan changes retain earlier versions. Changes after execution starts, conversation-brief replacements, milestone enrollment, and asynchronous inbox jobs need further impact/adapter work and are refused in this initial scope. An existing specialist-alternative route cannot bypass that restriction.

Accepted tasks do not automatically complete an objective. **Accept completed objective** requires every member assignment to have passed its existing output review, current artifact/evidence checks to pass, accounting to be resolved, open handoffs/disagreements to be resolved, and an owner statement that the recorded criteria are satisfied. This does not assert that a business outcome has been measured or that factual accuracy has been independently established.

The final WF02 candidate passed **565 existing regressions and 31 new objective integration tests** on Linux/Python 3.12.3, plus **47 overlapping local checks** on Windows/Python 3.13.0. Providers were fixtures and external networking was blocked. The roadmap's UP003/E003 entries record the exact tested source fingerprint and retained logs; this is implementation evidence, not production or live-model acceptance.

Enrollment is explicit and limited to unstarted root assignments without prior spending or handoffs. Existing work is not silently reclassified. The four additive `workforce_objective_*` / `workforce_objectives` tables store identity, membership, plans, and links to canonical costs; existing project/task/cost records remain authoritative. Repeated initialization preserves legacy permissions, spending, and history. Baseline source-restore tooling intentionally refuses to overwrite these new working-tree edits. Before any older-code rollback, stop/pause the worker and pause objective-managed assignments with the current controls; retain all objective/accounting tables and do not resume those assignments under code that ignores their limits. A reviewed release/rollback package remains WF01 work.

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

The roadmap specifies sequential initial workforce execution and a gate before adding parallel dispatch. The local WF02 candidate enforces cumulative limits for explicitly enrolled ordinary assignments. Reviewer-independence extensions, active work-graph migration/replanning, owner-approved evaluation rubrics, and production release acceptance remain open.

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
