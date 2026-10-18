# Superhuman Agentic Workforce Roadmap

Living requirements, implementation backlog, feedback, and engineering instructions.

**Created:** 18 October 2026  
**Last updated:** 18 October 2026  
**Document status:** Proposed implementation roadmap  
**Implementation status:** Changes below are not implemented unless their evidence and acceptance checks are recorded here.

## 1. Purpose and target

Superhuman should become a workforce that takes responsibility for an authorized objective, organizes the work, selects suitable specialists, executes with tools, checks the results, resolves ordinary problems, and follows through to a measurable outcome. The owner should be involved when a decision requires their judgment, information, or authority.

The immediate priority is to connect the existing agentic components into a continuous work lifecycle. Adding more employee personas alone will not accomplish this.

“Fully agentic” means dependable autonomy within explicit authority, privacy, time, and spending boundaries. The system must know what it may do, what it has actually done, what remains uncertain, and when to ask for help. Human strategic approval can remain part of that system.

This file is the central place to maintain the intended behavior, implementation status, owner feedback, decisions, and acceptance evidence. It is a roadmap, not authorization to deploy changes, alter permissions, spend money, or take external actions.

## 2. How to maintain this file

- Give each requirement its existing `WF` identifier when discussing work, feedback, commits, and verification.
- Keep requirement identifiers stable. Add new requirements rather than renumbering existing ones.
- Update the backlog status and the relevant detailed requirement after meaningful implementation work.
- Record changed files, verification results, limitations, and remaining work in the update log.
- Keep owner feedback verbatim in the feedback log. Record the resulting interpretation separately.
- Record material architecture and autonomy decisions in the decision log, including their scope and consequences.
- Check acceptance items only when supported by evidence. Code presence, a queued task, or a model's assertion is insufficient.
- Keep historical entries. Mark a requirement superseded and link its replacement instead of deleting its history.
- Store credentials and private source content in their designated systems. Use references or redacted examples here.

### Status definitions

| Status | Meaning |
| --- | --- |
| Proposed | Required change identified; implementation has not been verified |
| Ready | Scope, dependencies, and acceptance checks are sufficient to start |
| In progress | Implementation work is underway |
| Blocked | A named dependency or owner decision prevents progress |
| In validation | Implementation exists and is being checked |
| Complete | Acceptance checks pass and evidence is linked |
| Deferred | Deliberately postponed with a recorded reason |
| Superseded | Replaced by a linked requirement or decision |

**Priority:** P0 establishes the system and its credibility; P1 completes dependable execution; P2 improves scale, learning, and outcomes. These are engineering priorities for this roadmap, separate from application task priorities.

## 3. Current foundation

The review identified substantial foundations in the upgrade packages through v1.41:

- A persisted agent loop with tool selection, observations, execution records, and evidence references.
- Specialist identities, task ownership, dependencies, handoffs, and disagreements.
- Project leads, milestone contributions, independent specialist reviews, Twin review, and owner decisions.
- Scoped memory, shared organisational context, source grants, and freshness checks.
- Cost accounting, request limits, execution limits, pause and cancellation controls.
- Proactive signals, research-gap investigations, and outcome metric records.

Preserve and extend these components. Do not duplicate them in a new scheduler or replace their recorded history without an explicit migration design.

The initial review found an older local `superhuman/` tree with several newer modules missing, and did not establish the server version. Subsequent WF01 reconciliation captured the complete owner-confirmed server source, whose markers report 1.41.0, and consolidated it locally. The initial 218-file syntax check was not an integrated regression run; UP002 records the later complete-source regression results. All provider behavior in those regressions uses fixtures; live checks remain outstanding.

### Main gaps

1. A verified current source snapshot is now available; release reproducibility and complete migration/restore validation remain unfinished.
2. Conversation execution is narrower than the broader planning and collaboration machinery.
3. Recovery often ends in a manual hold.
4. Operational tools cannot yet complete many real business responsibilities.
5. Retrieval and evidence checks do not establish complete source coverage or factual correctness.
6. Scheduling, procedural learning, and outcome follow-through need stronger feedback loops.
7. Real multi-specialist competence has not been demonstrated by the reviewed test evidence.

## 4. Required work at a glance

All statuses below refer to the proposed changes, including extensions of capabilities that already exist.

| ID | Required change | Priority | Status | Main dependencies |
| --- | --- | --- | --- | --- |
| WF01 | Consolidate the current application and release process | P0 | In progress | None |
| WF02 | Establish one persistent objective and work lifecycle | P0 | In progress | WF01 |
| WF03 | Connect conversation to planning and execution | P0 | Proposed | WF02, WF04 |
| WF04 | Define explicit delegated authority | P0 | Proposed | WF01 |
| WF05 | Complete dynamic planning and collaboration | P1 | Proposed | WF02, WF04 |
| WF06 | Add dependable recovery and reconciliation | P1 | Proposed | WF02, WF04 |
| WF07 | Extend governed operational tools | P1 | Proposed | WF04, WF06 |
| WF08 | Improve retrieval and source coverage | P1 | Proposed | WF01, WF02 |
| WF09 | Connect claims to evidence and quality review | P1 | Proposed | WF05, WF08 |
| WF10 | Schedule by capacity and capability | P2 | Proposed | WF02, WF05, WF06 |
| WF11 | Turn feedback into evaluated procedural learning | P2 | Proposed | WF09, WF14 |
| WF12 | Complete proactive follow-through and outcome measurement | P2 | Proposed | WF02, WF04, WF09 |
| WF13 | Unify owner visibility and intervention controls | P1 | In progress | WF02, WF03, WF06 |
| WF14 | Establish realistic evaluations and release gates | P0 | In progress | Starts with WF01; expands with every requirement |
| WF15 | Establish operational reliability and security checks | P1 | Proposed | WF01, WF04, WF06 |

## 5. Detailed requirements

### WF01 Consolidate the current application and release process

**Current position:** The local application is consolidated from the verified v1.41 server source, with per-file provenance and its prior source backed up. Upgrade packages remain historical. Complete release reproducibility, loaded-process attestation, and migration/restore compatibility still require evidence; package presence alone proves none of them.

**Initial local baseline, before server reconciliation:** `tools/workforce_baseline.py` provided a repeatable, application-import-free local inventory. The run at checkout base `26e3fbbee4bad6cdbe4fbf1709edb4fd2fb13add` found 60 Python source files with valid syntax, seven database schemas inspected without reading business rows, and valid payload hashes for all 87 manifest entries across v1.37–v1.41 (counts overlap across releases). Of the 17 v1.41 paths, 15 were absent locally and two differed byte-for-byte; none matched the payload. Installed OpenAI 3.31.0 and ReportLab 5.0.1 exceeded the v19 specification's upper bounds. Cryptography was declared separately by v1.12 and absent from the original local environment listing. Runtime, deployed version, service definitions, source consolidation, and integrated regressions were then unverified. UP002 records the later reconciliation and tests. The original `baseline-local.json` is retained locally as pre-consolidation evidence and ignored by Git because it contains host metadata.

**Required changes:**

- Identify the installed version and its exact source, configuration schema, service definitions, and database migration state through an authorized read-only inventory.
- Produce one authoritative application source tree with the latest intended behavior. Preserve upgrade packages as release history.
- Establish a reproducible dependency specification, documented startup commands, and automated build and regression checks.
- Convert necessary installation-time source transformations into reviewed application changes and explicit migrations.
- Define database and artifact backup, restore, migration, and rollback behavior. Preserve business records, permissions, spending, and audit history.
- Update the root README so it describes the current system and its actual limitations.

**Acceptance checks:**

- [ ] A clean checkout can install and run the current application using documented commands.
- [ ] Local, test, and deployed releases can report their version, commit, and schema version.
- [ ] Representative existing records survive migration and rollback rehearsals.
- [x] Integrated checks run against the assembled application, not only isolated upgrade payloads. See E002; provider competence and complete migration acceptance remain open.

### WF02 Establish one persistent objective and work lifecycle

**Local implementation scope, 18 October 2026:** Explicit enrollment of an unstarted ordinary root assignment creates one objective inside its existing business project. Conversation origin IDs and the exact owner request are retained when present; independent requests in a shared conversation container are not merged. Future handoffs inherit membership. The canonical task/run records and `team_costs` ledger remain authoritative. Objective-scoped Twin coordination, execution, draft subrequests, and review calls share cumulative allowances and sequential execution guards. Four additive tables hold objective identity, assignment links, plan history, and cost links. Owner views expose state, usage, linked tasks, plans, controls, and final acceptance. See UP003/E003 for implementation evidence.

**Initial limits:** Existing running/historical work is not automatically enrolled; enrollment rejects prior run/spend/handoff history instead of resetting it. Milestone work-package migration is not implemented. Brief revisions are allowed before execution only, with an impact note and retained plan history; post-start alternatives and conversation brief replacements are blocked pending the WF03/WF05 impact workflow. Formal output revisions consume the shared revision allowance. Autonomous graph replanning, independent reviewer extensions, and outcome follow-up remain open. This local candidate is not a production deployment or a completed WF02 release.

**Initial record mapping (before schema changes):** Use `team_projects.id` as the business project container and `team_tasks.id` for specialist assignments. `team_tasks.run_id` links to the execution `projects.id` / `agentic_runs.project_id`; those execution projects are not separate business objectives. `milestones.project_id` links the business container to versioned work packages and reviews. `conversation_jobs.turn_id`, `task_id`, and `project_id` preserve origin links. Unlinked conversation containers currently group multiple independent requests, so a container must not automatically become one objective or one shared allowance. WF02 must introduce an objective identity within the existing business project and map its tasks, revisions, handoffs, and origin turns explicitly; do not add a second task queue or change historical grouping. Approval and allowance records must identify that objective, not merely its conversation or department.

**Required changes:**

- Make the existing project and task records the basis for a canonical objective record; document the mapping before adding schema.
- Retain the owner request, clarified brief, success criteria, accountable lead, plan versions, assignments, dependencies, artifacts, evidence, authority, spending, deadlines, blockers, and outcome measures.
- Connect conversations, employee tasks, agent runs, milestones, and reviews through stable identifiers.
- Define explicit state transitions and the actor permitted to make each transition.
- Distinguish a task finishing, a deliverable being accepted, an objective being completed, and a business outcome being measured.
- Preserve obsolete plan versions and mark affected outputs when assumptions or requirements change.
- Enforce one cumulative objective allowance across child tasks, delegation, retries, reviews, revisions, and replans. Record maximum spending, elapsed wall time, model requests, and revision rounds before dispatch. Pausing does not reset the elapsed deadline; resuming, restarting, or replacing a plan does not reset consumption.
- Reserve shared allowances transactionally before dispatch. Retain reservations for uncertain paid outcomes until reconciled; settle confirmed usage without double charging. Exhausted or missing allowances hold new work with a precise reason. Only authorized changes may increase limits, preserving earlier consumption and the change history.

**Acceptance checks:**

- [ ] One objective can be followed from the original message through work, review, and outcome follow-up.
- [x] Restarting a worker or opening another interface preserves the same work state for the initial enrolled-assignment scope. Fresh-process and owner-route checks are recorded in E003.
- [ ] Completion requires the recorded success criteria and mandatory reviews to be satisfied.
- [ ] Changes to the brief produce an explicit plan revision and impact assessment.
- [x] Nested delegation and formal output/initial-plan revisions share cumulative allowances; restart and resume preserve consumption. Active-work replanning remains refused pending its impact workflow, rather than creating untracked iterations. See E003.
- [x] Concurrent dispatch/reservations competing for the last available allowance admit only affordable work in the initial scope. Unknown usage remains reserved and repeated settlement cannot double charge or release it. See E003.
- [x] Reaching an applicable limit blocks the affected new work and produces an actionable blocker without discarding completed work. A zero revision allowance blocks revisions, not the initial assignment. See E003.

### WF03 Connect conversation to planning and execution

**Current position:** v1.41 connects an explicit owner request to one bounded research or drafting job. Broader planning and collaboration use separate workflows.

**Required changes:**

- Classify messages as discussion, clarification, a new work request, feedback, or a change to existing work.
- Reuse the canonical objective and existing governed execution pipeline for requests involving multiple steps or specialists.
- Clarify only information that materially affects execution. Let routine implementation choices proceed within delegated authority.
- Resolve references such as “continue this,” “use the report,” and “ask Sam to review it” to actual permitted work and artifacts.
- Return progress, blockers, review requests, and results to the source conversation.
- Deduplicate repeated submissions and preserve the distinction between owner instructions and quoted or retrieved content.

**Acceptance checks:**

- [ ] A single owner request can initiate research, analysis, specialist review, revision, and a final deliverable.
- [ ] Follow-up feedback modifies the existing objective without creating disconnected duplicate work.
- [ ] The same routine authorization is not requested again at each internal step.
- [ ] Progress claims match persisted execution state and actual evidence.

### WF04 Define explicit delegated authority

**Required changes:**

- Extend existing grants into inspectable authority records covering the objective, actors, tools, data, external destinations, action types, cost ceilings, expiry, and escalation conditions.
- Separate permission to read, prepare, modify, send, publish, submit, and spend.
- Allow the owner to delegate a bounded class of routine work without approving each invocation.
- Revalidate current authority immediately before consequential execution. Invalidate prepared actions when their material content changes.
- Retain source classification and project boundaries through handoffs, exports, and external calls.
- Define when owner judgment remains mandatory, including strategic changes and actions outside the delegation.

**Acceptance checks:**

- [ ] Every executed action has a traceable authority basis.
- [ ] Expired or revoked authority blocks the next affected action.
- [ ] A specialist cannot broaden access or authority by delegating work.
- [ ] A material change to recipients, payload, spending, or destination triggers the appropriate recheck.

### WF05 Complete dynamic planning and collaboration

**Required changes:**

- Extend existing milestone plans into versioned work graphs with dependencies, deliverables, criteria, owners, effort estimates, and review assignments.
- Select specialists using relevant capabilities and permitted tools as well as department identity.
- Define handoff contracts containing the question, expected output, required evidence, dependencies, classification, deadline, and receiving owner.
- Execute initial specialist contributions sequentially. Enable bounded parallel contributions only after the concurrency gate below passes; independent graph nodes alone do not authorize parallel dispatch.
- Let leads resolve routine disagreement using recorded evidence and escalate material unresolved conflicts.
- Replan when new evidence invalidates assumptions, a dependency fails, or a deliverable is rejected, while respecting existing strategic boundaries.

**Acceptance checks:**

- [ ] At least three specialists complete a real assignment with explicit contributions and an integrated result.
- [ ] Handoffs transfer sufficient permitted context and return results to the parent work.
- [ ] Dependency cycles, abandoned handoffs, and conflicting ownership are detected.
- [ ] Plan changes preserve completed work where valid and explain invalidated work.
- [ ] Parallel dispatch remains disabled until WF06 lease/recovery checks, WF02 atomic allowance checks, cancellation propagation, duplicate-dispatch checks, and database-contention tests pass against the integrated application. Record evidence and the enabling decision before changing this mode.

### WF06 Add dependable recovery and reconciliation

**Current position:** Durable records and conservative interruption holds exist. They need a more complete recovery policy.

**Required changes:**

- Categorize failures as transient, invalid arguments, unavailable capability, quality failure, permission failure, or uncertain external outcome.
- Assign each tool an explicit replay policy, idempotency strategy, timeout, checkpoint, and reconciliation method.
- Retry safe transient operations within attempt, time, and cost limits. Never blindly replay an uncertain external write or paid operation.
- Reconcile provider job identifiers and external receipts before deciding whether execution failed.
- Persist resumable checkpoints, bounded backoff, worker leases, and a queue for failures requiring inspection.
- Generate a useful blocker report with what happened, what was preserved, what can resume, and what decision is needed.

**Acceptance checks:**

- [ ] Worker termination during representative stages does not lose work or duplicate external effects.
- [ ] A known safe transient failure recovers within its limits.
- [ ] An uncertain side effect is reconciled or held with actionable evidence.
- [ ] Cancellation and pause prevent subsequent unauthorized steps even if an in-flight call finishes.

### WF07 Extend governed operational tools

**Required changes:**

- Prioritize integrations from actual owner workflows: email delivery, calendar actions, document updates, repository operations, CRM updates, publishing, or submissions.
- For each adapter define typed inputs, required authority, permitted data, validation, execution receipt, verification, idempotency, and recovery behavior.
- Prepare reviewable payloads for actions needing approval and bind approval to their material content.
- Verify remote state after execution; distinguish accepted, queued, delivered, rejected, and unknown outcomes.
- Improve deliverable production where needed, including document layout checks, meaningful spreadsheet formulas and recalculation, and coding workflows appropriate to the assignment.
- Add connector health, credential expiry, rate-limit handling, and scoped credential access.

**Acceptance checks:**

- [ ] Each adopted integration completes a representative real workflow and records a verifiable receipt.
- [ ] Required approval applies to the actual executed payload.
- [ ] Failed or repeated execution cannot silently create duplicate transactions.
- [ ] The system explains unavailable capabilities before promising execution.

### WF08 Improve retrieval and source coverage

**Current position:** Existing storage search uses keyword matching and bounded excerpts. Tools can read PDF text pages, but do not provide OCR.

**Required changes:**

- Index permitted documents into versioned chunks with page or section locations, source identity, classification, and freshness metadata.
- Evaluate hybrid keyword and semantic retrieval with reranking against real department questions; choose methods based on measured retrieval quality.
- Track which pages and requirements have been examined for tasks requiring complete document coverage.
- Provide OCR when scanned documents are in scope and preserve extraction confidence and layout limitations.
- Support deliberate retrieval of complete relevant sections instead of silently relying on excerpts.
- Invalidate affected retrieval results and derived work when sources change or access is withdrawn.

**Acceptance checks:**

- [ ] A representative long guide produces a coverage record with every required section addressed or explicitly unresolved.
- [ ] Relevant evidence is found across the test corpus with recorded retrieval results and misses.
- [ ] Missing pages, extraction failures, and stale evidence block unsupported completeness claims.
- [ ] Retrieval respects current permissions before supplying content to a model.

### WF09 Connect claims to evidence and quality review

**Required changes:**

- Extend existing assurance records to ordinary research and drafting where factual support matters.
- Link material claims to exact supporting passages, source versions, dates, and reviewer judgments.
- Distinguish source existence, quotation accuracy, relevance, factual support, and completeness.
- Check conflicting evidence and unresolved assumptions. Separate owner-provided business facts from externally verified findings.
- Use a separate reviewer assignment and execution context for material deliverables. The reviewer must not have authored or revised the artifact under review; a different persona name alone is insufficient. Give the reviewer the brief, permitted sources, and rubric, and require their own evidence assessment.
- Bind each review to an immutable artifact version or hash and rubric version. Material revisions invalidate earlier approval. Record defects, severity, disposition, and reviewer identity; unresolved material defects hold acceptance and unresolved disagreements go to the authorized decision maker.
- Define completion thresholds by work type, including factual accuracy, requirement coverage, usability, and artifact quality.

**Acceptance checks:**

- [ ] A materially unsupported claim prevents acceptance or is explicitly qualified in the deliverable.
- [ ] Important claims can be traced to accessible source passages.
- [ ] Review decisions identify concrete defects and required revisions.
- [ ] Changing an accepted source identifies and flags affected outputs.
- [ ] Self-review is rejected, changed artifacts cannot reuse approval, and unresolved material defects prevent acceptance. A separate reviewer can return a supported rejection and verify the resulting revision.

### WF10 Schedule by capacity and capability

**Required changes:**

- Extend existing priority and dependency scheduling with deadlines, expected duration, resource use, and specialist availability.
- Record capability profiles and measured performance by task type rather than assuming every named specialist is equally capable.
- Estimate request and tool costs before dispatch; account for review and likely revision costs.
- Introduce parallel execution only after leases, resource limits, cancellation, and database contention are verified.
- Prevent starvation across objectives and distinguish blocked work from work actively consuming capacity.
- Use capability-tested model routing where appropriate; preserve explicit model and budget policies.

**Acceptance checks:**

- [ ] Independent work can run concurrently without duplicate claims or budget overspend.
- [ ] Deadline conflicts and infeasible commitments are visible before they become overdue.
- [ ] Routing decisions show capability, authority, capacity, and cost considerations.
- [ ] Lower-priority objectives continue to make bounded progress.

### WF11 Turn feedback into evaluated procedural learning

**Required changes:**

- Link owner corrections, review failures, and accepted revisions to their task, artifact, and root cause.
- Propose specific changes to procedures, prompts, examples, retrieval rules, or tool contracts when repeated failures justify them.
- Keep factual memory, preferences, and procedural skills separately classified and versioned.
- Evaluate a proposed skill change against a regression set before promotion; record the approving authority.
- Retain prior versions and support rollback when a change causes regressions.
- Measure whether the same defect recurs after the change.

**Acceptance checks:**

- [ ] A recurring failure produces a reviewable improvement proposal with supporting examples.
- [ ] Promotion requires evidence of improvement without unacceptable regressions.
- [ ] Skills can be traced to their version, evaluation, and approval.
- [ ] Private project content does not become a broadly shared skill example without authority.

### WF12 Complete proactive follow-through and outcome measurement

**Current position:** Proactive alerts and source-backed outcome records already exist. Their collection and resolution loops need completion.

**Required changes:**

- Associate each signal with an accountable actor, next action, deadline, and resolution condition.
- Turn eligible signals into bounded internal work under existing authority; ask for owner judgment when authority is insufficient.
- Deduplicate repeated alerts and track acknowledgement separately from resolution.
- Define outcome metrics with collection method, baseline, target, units, observation frequency, owner, and evidence requirements.
- Collect measurements through permitted connectors or explicit owner input and review their freshness.
- Compare results with targets, diagnose shortfalls, and propose changes without asserting unsupported causal attribution or ROI.

**Acceptance checks:**

- [ ] A stalled task leads to an investigation, resolution, or explicit escalation.
- [ ] An outcome review obtains a current observation or records a specific collection blocker.
- [ ] A missed target produces a supported adjustment proposal linked to its objective.
- [ ] Notifications stop only when their resolution condition is satisfied or deliberately waived by the appropriate authority.

### WF13 Unify owner visibility and intervention controls

**Required changes:**

- Show objectives, current plans, active employees, completed artifacts, blockers, reviews, spending, and next actions in one coherent view.
- Let the owner inspect the authority and execution evidence behind any action.
- Provide consistent pause, resume, cancel, reprioritize, revise, and approve controls across conversation and task views.
- Present precise questions with the prepared work, relevant evidence, available options, and effect on progress.
- Supply concise scheduled or event-driven progress summaries under owner preferences.
- Distinguish operational receipts from model-generated summaries in all status displays.

**Acceptance checks:**

- [ ] The owner can determine who owns each objective, what happened, what is blocked, and what happens next.
- [ ] A correction from the owner reaches all affected assignments.
- [ ] Controls have consistent behavior across interfaces and survive restart.
- [ ] The system never labels a queued operation or unreviewed output as a verified completed outcome.

### WF14 Establish realistic evaluations and release gates

**Required changes:**

- Keep deterministic regression tests and add integrated tests against the authoritative application.
- Build a representative evaluation set covering each specialist's real responsibilities, tool use, retrieval, collaboration, and final artifacts.
- Include fault injection for provider errors, worker restarts, stale context, changed permissions, missing evidence, cancellation, and uncertain outcomes.
- Run controlled live acceptance assignments with explicit test budgets and measure real provider behavior and receipts.
- Track accuracy, completeness, evidence support, task completion rate, intervention count, latency, cost, duplicate effects, and recurring defects.
- Version evaluation datasets, rubrics, models, prompts, tools, and results so release comparisons are meaningful.
- Freeze an owner-approved, versioned workflow rubric before candidate acceptance evaluation begins. Specify dataset, scoring rules, accuracy, coverage, completion, allowed interventions, latency, total cost, duplicate effects, and mandatory authority/security checks. Missing thresholds block acceptance evaluation, not exploratory baseline measurements.
- Record threshold changes as new decisions and rubric versions with their rationale. Re-evaluate the candidate under the new version; do not relabel an earlier failing run as a pass.

**Acceptance checks:**

- [ ] A complete multi-specialist workflow passes with actual providers and saved evidence.
- [ ] A reviewer can reproduce each evaluation and distinguish fixtures from live results.
- [ ] Candidate releases meet documented quality and reliability thresholds before deployment.
- [ ] Security and authority failures block release regardless of aggregate task scores.
- [ ] Each acceptance run references a rubric approved before its start; absent approval or retroactive threshold changes cannot produce a release pass.

### WF15 Establish operational reliability and security checks

**Required changes:**

- Verify authentication, authorization, session protection, source isolation, credential handling, and tool isolation in the consolidated application.
- Enforce least privilege at execution boundaries; do not rely solely on model instructions.
- Add prompt-injection and data-exfiltration evaluations using untrusted documents, inbox content, web pages, and tool observations.
- Correlate objective, task, run, tool action, provider request, cost reservation, and final receipt in operational telemetry.
- Add monitoring for stuck work, unexpected spending, repeated failures, unavailable connectors, and reconciliation discrepancies.
- Exercise backup restoration, retention and deletion procedures, audit access, service restart, and incident response.

**Acceptance checks:**

- [ ] Cross-project access and unauthorized external actions fail at enforced boundaries.
- [ ] Malicious source instructions do not acquire execution authority or reveal protected data.
- [ ] A restore rehearsal recovers representative business records and execution history.
- [ ] Operators can diagnose a failed objective without exposing credentials or unrestricted private content in logs.

## 6. Target architecture and data contracts

Use the existing project, task, runtime, team, milestone, assurance, storage, and budget components as the starting point. Establish the following contracts before introducing additional orchestration services.

| Contract | Required information |
| --- | --- |
| Objective | Owner request, scope, criteria, lead, current plan, authority, cumulative limits and reservations, deadline, consumption, state, outcome measures |
| Plan version | Steps, dependencies, assignments, estimates, assumptions, changes, impact on earlier work |
| Assignment | Accountable specialist, brief, inputs, output contract, acceptance criteria, classification, deadline |
| Action | Tool and version, typed arguments, authority basis, idempotency key, lease, state, receipt, cost |
| Evidence | Claim or requirement, source and version, locator, passage, support judgment, freshness, access |
| Review | Separate reviewer assignment and authorship check, exact artifact hash, rubric version, evidence assessment, defects and disposition, decision, revision request |
| Learning proposal | Failure examples, proposed procedure change, evaluation, approval, version, rollback reference |
| Outcome observation | Metric, units, observation date, source, value, freshness, review state |

All interfaces should operate on the same underlying work records. Events should carry stable correlation identifiers and distinguish requested, authorized, started, observed, verified, and accepted states. Persisting an execution receipt and updating its task state must have a documented consistency strategy.

Use an outbox or equivalent durable mechanism when dispatch must cross process boundaries. Assume delivery may occur more than once; make handlers idempotent. Do not promise exactly-once external side effects without support from the destination system.

## 7. Implementation sequence

The sequence below is dependency driven. Dates and effort estimates should be added after WF01 establishes the actual application baseline.

### Phase A Establish the baseline

Implement WF01, the initial authority model in WF04, and the evaluation harness in WF14. Inventory existing behavior before changing it. Reconcile current source and deployment state, rehearse migration, and preserve real data.

**Exit:** A reproducible current build, verified migrations, and a baseline evaluation report.

### Phase B Connect the work lifecycle

Implement WF02 and WF03, then extend WF05 and WF13. Include WF09 reviewer separation and artifact-version checks from the start. Demonstrate one owner request progressing sequentially through specialist work, review, revision, and final acceptance using the same objective and cumulative allowance. This phase does not enable parallel dispatch.

**Exit:** A real multi-specialist assignment completes without manual copying between disconnected workflows.

### Phase C Make execution dependable

Implement WF06, WF08, the remaining WF09 checks, and the relevant WF15 checks. Validate interruption recovery, source coverage, evidence support, and control consistency before broadening external authority. Complete the WF05 concurrency gate here or later before enabling parallel execution; concurrency is not required to pass the sequential workflow.

**Exit:** Failure scenarios recover or escalate correctly; long-source and evidence evaluations pass.

### Phase D Complete operational responsibilities

Implement selected WF07 adapters and initial WF10 scheduling improvements. Start with workflows of known value and clearly bounded authority.

**Exit:** At least one real external workflow completes with appropriate authorization, remote verification, and no duplicate effects.

### Phase E Improve through outcomes

Implement WF11 and WF12 and expand WF10 as demand justifies it. Evaluate whether learning and proactive work reduce intervention and improve measured outcomes.

**Exit:** A measured outcome leads to a supported adjustment, and a procedural improvement reduces a recurring defect.

## 8. Reference acceptance scenario

Use an owner-approved business-plan research assignment as a representative scenario. The exact business and regulatory facts must be verified during execution.

1. The owner asks Katherine to research current official guidance, compare it with an uploaded guide, identify gaps, obtain Sam's review, and prepare a recommendation.
2. Superhuman creates one objective, identifies missing essential information, and records authority and limits.
3. The lead builds a plan and assigns research, document coverage, analysis, and independent review.
4. Specialists retrieve permitted sources, record coverage, and link material claims to evidence.
5. An injected transient failure recovers safely; an uncertain paid operation is reconciled or held without automatic replay.
6. The reviewer identifies a concrete weakness. The responsible specialist revises the same work, preserving prior versions.
7. The lead integrates the results. The Twin checks the criteria and forwards strategic decisions to the owner.
8. The final artifact returns to the original conversation with evidence, limitations, review status, and actual spending.
9. The owner provides feedback. The system updates the objective and proposes a procedural improvement if appropriate.
10. The agreed follow-up date produces an outcome check and a supported next action.

Record the run IDs, artifacts, provider receipts, observed defects, interventions, and results in the acceptance record below. A successful acknowledgement or queue entry does not constitute a pass.

## 9. Definition of done for the workforce

The system can be considered ready for the intended operating scope when all required P0 and P1 requirements pass, relevant P2 capabilities meet the owner's operating needs, and the following evidence is available:

- [ ] One reproducible source and release process matches the running system.
- [ ] Authorized objectives persist across conversation, planning, execution, review, and outcome follow-up.
- [ ] Specialists collaborate and replan with clear ownership and enforceable authority.
- [ ] Operational integrations complete the selected real responsibilities.
- [ ] Recovery handles representative failures without duplicate effects or unaccounted work.
- [ ] Required source coverage and material claims have inspectable evidence.
- [ ] The owner can intervene without manually coordinating every routine step.
- [ ] Spending, time, quality, and intervention metrics meet agreed release thresholds.
- [ ] Learning changes are evaluated and reversible.
- [ ] Live evaluations and operational rehearsals support the claimed level of autonomy.

Thresholds such as completion rate, acceptable intervention count, maximum cost, and deadline tolerance must be agreed for each workflow. Do not invent or silently relax them to declare success.

## 10. Engineering instructions

These instructions apply when implementing this roadmap within the owner's authorized task scope.

1. Inspect the current application and applicable repository instructions before editing. Do not assume a package is installed because its folder exists.
2. Map each change to a requirement ID and state its acceptance checks before implementation.
3. Extend existing authoritative records and workflows wherever practical. Explain any new scheduler, queue, database, or orchestration layer before adding it.
4. Preserve task history, artifacts, evidence, permissions, and cost accounting through migrations.
5. Use structured tool contracts and explicit state transitions. A prompt instruction is insufficient enforcement for authority, privacy, or budgets.
6. Keep external side effects separate from generation. Verify the actual prepared payload, authority, remote result, and receipt.
7. Do not replay uncertain operations merely because a timeout occurred. Reconcile first.
8. Keep user-facing status grounded in persisted facts. Label limitations and unresolved evidence accurately.
9. Use meaningful tests for the changed behavior, integrated checks for connected workflows, and live validation only within explicit authority and budgets.
10. Update this file with implementation evidence and remaining limits. Do not mark a requirement complete based only on code presence or fixture success.
11. Treat optional infrastructure choices as decisions to justify, not prerequisites by default. Additional frameworks, vector stores, model providers, or distributed services need demonstrated value.
12. Record scope changes and owner feedback without overwriting earlier decisions or attributing inferred preferences to the owner.

## 11. Owner decisions to record

These decisions can be resolved as the relevant implementation phase approaches. They need not prevent independent baseline work.

| Decision ID | Topic | Decision needed | State |
| --- | --- | --- | --- |
| D01 | Initial workflows | Which real responsibilities should pass first | Open |
| D02 | Delegated autonomy | Which actions may proceed routinely and within what limits | Open |
| D03 | External integrations | First systems to support and permitted data access | Open |
| D04 | Quality thresholds | Versioned workflow rubric and accuracy, completion, intervention, time, and cost levels; approval required before candidate acceptance evaluation starts | Open; baseline measurements may proceed |
| D05 | Strategic authority | Decisions always reserved for the owner | Open |
| D06 | Measurement | Initial business outcomes and collection methods | Open |
| D07 | Operating scope | Personal workforce only or future support for multiple human users | Open |

## 12. Feedback log

Add one entry per substantive feedback item. Preserve the original wording when available.

### FB001 — 18 October 2026

- From: Owner.
- Related requirements: WF01, WF02, WF05, WF06, WF09, WF14.
- Original feedback: "Proceed with the implementation".
- Interpretation: Proceed with the action plan proposed in the conversation, beginning with roadmap rules and baseline reconciliation; this does not establish numeric business thresholds or a live provider spending allowance.
- Status: In progress. Roadmap rules, tooling, and deployed-source reconciliation delivered; application enforcement extensions remain outstanding. See UP002 for subsequent work.
- Evidence: UP001 and E001 below.

### FB002 — 18 October 2026

- From: Owner.
- Related requirement: WF01.
- Original feedback: "yes thats where it is".
- Context: Confirmation that the running checkout is `/home/superhuman/app` on `167.71.196.20`.
- Interpretation: Use that checkout for baseline reconciliation. This confirms the location; source hashes and service inspection provide the implementation evidence.
- Status: Location resolved; server inventory and source capture completed. See UP002.

### FB003 — 18 October 2026

- From: Owner.
- Related requirements: WF02, WF13, WF14; sequential-execution portion of WF05.
- Original feedback: "Proceed with the implementation".
- Interpretation: Continue from the reconciled source with persistent objective identity and cumulative execution limits. Implement and verify the local candidate without inventing business-quality thresholds, new source grants, or production deployment authority.
- Status: Local objective implementation and focused verification delivered; complete final-snapshot regression validation recorded in UP003/E003.

```text
Feedback ID: FB001
Date:
From:
Related requirement IDs:
Original feedback:
Observed example or run ID:
Interpretation or clarification:
Proposed change:
Acceptance check:
Status:
Resolution and evidence:
```

## 13. Decision log

### D08 Initial execution and evaluation rules — 18 October 2026

- Related requirements: WF02, WF05, WF06, WF09, WF14.
- Authority: Owner instruction, "Proceed with the implementation", following the proposed action plan.
- Decision: Start sequentially; enforce cumulative objective allowances; separate reviewer execution and artifact-bound approvals; freeze approved rubrics before acceptance evaluations.
- Consequences: Parallel dispatch requires recorded concurrency evidence. Numeric business thresholds and live provider spending limits remain owner decisions; none are invented here.
- Revisit condition: Integrated concurrency evidence or a versioned owner-approved rubric change. Preserve earlier decisions and evaluation results.

### D09 Source reconciliation — 18 October 2026

- Related requirement: WF01.
- Authority: Owner confirmed the running checkout location following authorization to implement the action plan.
- Decision: Capture and hash-verify the current server source, test it in isolated state, and use it to consolidate the local application while retaining prior local source in a private backup. Preserve the package directories as history.
- Evidence: Server source reports 1.41.0 in both boundary and repair version markers; all 17 v1.41 payload files match. Both systemd services report active/running as `superhuman`, with `/home/superhuman/app` as WorkingDirectory. The server checkout has no Git repository.
- Consequences: Source fingerprint and per-file hashes establish the captured baseline. Service status and source markers do not attest to an already running process's loaded source or validate real provider competence. No production source, service, configuration, permission, or budget changes are included in this consolidation.
- Revisit condition: Server source changes, divergent local edits, or a reviewed new release.

### D10 Initial objective implementation boundaries — 18 October 2026

- Related requirements: WF02, WF05, WF13, WF14.
- Authority: Owner instruction to proceed with implementation after source reconciliation; routine design choices within that scope.
- Decision: Add explicit objective identity within existing business projects and retain canonical team tasks, execution projects/runs, and cost accounting. Ordinary unstarted root assignments are opt-in; task membership is immutable and inherited by handoffs. Do not infer a single objective from a conversation collection or silently enroll existing spend/runs.
- Limits: Owner-entered cumulative dollar, request-attempt, total wall-time, and formal revision allowances. Deadlines remain anchored to creation; reservations and request attempts survive pause/resume/restart and total-limit amendments. Failed local preparation before a provider call may release proven-unused dollars but not reset the recorded attempt. All objective-scoped coordinator/review/execution calls are linked to the same canonical ledger, across budget periods.
- Execution: Use existing worker/scheduler and enforce one dispatched assignment and one in-flight provider reservation per objective. Recheck state immediately before provider/tool execution. Async inbox work is refused until an objective-bound adapter exists.
- Completion: Reuse existing output reviews and artifact/evidence contracts, then require explicit owner acceptance of criteria. Business outcome measurement and independent reviewer extensions are separate unfinished work.
- Compatibility: Preserve legacy work unchanged. Refuse milestone enrollment and post-start/conversation brief changes until their migration/impact design exists; prevent the older alternative-instruction route from bypassing that boundary. Rollback requires worker/assignment quarantine and retained accounting, not deletion of the new tables or automatic resumption under older code.
- Revisit condition: WF03 conversation feedback/impact propagation, WF05 versioned active work graphs, milestone migration evidence, and the WF09/WF14 quality and release gates.

```text
Decision ID:
Date:
Related requirement IDs:
Decision maker:
Decision:
Scope and authority:
Reason and alternatives considered:
Consequences:
Revisit condition:
Supersedes or superseded by:
```

## 14. Implementation update log

### 18 October 2026 Roadmap created

- Established WF01 through WF15 from the codebase evaluation.
- Distinguished existing foundations from required extensions.
- Added implementation phases, acceptance checks, engineering instructions, and maintenance logs.
- No application implementation, deployment, permission change, or live provider validation was performed as part of creating this file.

### UP001 — 18 October 2026 Baseline tooling and implementation gates

- Related requirements: WF01, WF02, WF05, WF06, WF09, WF14.
- Changes: Added `tools/workforce_baseline.py` and `tests/test_workforce_baseline.py`; updated this roadmap, root `README.md`, and `.gitignore`.
- Rules: Sequential initial execution; prerequisite concurrency gate; cumulative objective allowances and uncertain-usage reservations; separate artifact-bound review; rubrics approved before acceptance evaluation and re-evaluation after threshold changes.
- Verification: `.venv/Scripts/python.exe -m unittest discover -s tests -v` — four tests passed. Tests cover private-value exclusion without importing the app, unchanged database bytes and row privacy, payload tampering versus installation claims, and manifest path traversal rejection. `.venv/Scripts/python.exe tools/workforce_baseline.py --include-schema` — local inventory completed.
- Results: Local application source fingerprint `b5b152ae07c61d5f8a34a9c97b7b0eb7a4ae1ecdd15ccf945f97f1f010ad8620`. Counts and limitations appear under WF01. This fingerprint covers inventoried source, not a complete deployment bundle.
- Migration/configuration effects: None. No app modules, credentials, permissions, budgets, or business records were changed; no provider calls or deployment occurred.
- Status: WF01 moved to In progress. Other requirements retain Proposed status because their application behavior is not implemented by these documentation changes. No full requirement acceptance check was marked complete.
- Next action: Reconcile the actual running checkout with the local inventory, preserve a source/data backup, and assemble a reviewed current tree before modifying its execution pipeline. The package guide's server location has been presented to the owner for confirmation; it has not been treated as evidence of current deployment state.

### UP002 — 18 October 2026 Server reconciliation and local source consolidation

- Related requirements: WF01, initial offline harness under WF14; WF02 record mapping documented before schema changes.
- Authorization: Owner confirmed the server location in FB002 after authorizing implementation. Production access was limited to source/schema/service/dependency inspection and isolated fixture tests; no deployment was performed.
- Server findings: Python 3.12.3; both services active/running as `superhuman` in `/home/superhuman/app`; no Git checkout; source version markers 1.41.0; all 17 latest manifest files match. Read-only inventory recorded eight schema fingerprints and six known migration IDs across mailflow, milestone, practice, and UX marker tables, excluding business rows and configuration values.
- Source: Captured and verified 239 application files, including 218 Python modules, packaged organisation seed, static code, and eight portraits. Fingerprint: `05980ffa2494833617d75c270248b38ff0b954237dad49ea7043106b4d18025d`. Promoted the exact snapshot into local `superhuman/`, adding or changing 196 files. Preserved all 60 prior local source files in `.workforce/local-before-v141`, with a consolidation receipt and guarded source-restore tooling. `source-provenance.json` records every captured file hash; `.gitattributes` preserves application source bytes across platforms.
- Dependency work: Added `requirements-server-v141.lock` from observed package versions; `requirements.txt` now includes it. Fresh isolated Windows/Python 3.13 dependency installation and `pip check` pass. Added pinned Windows `tzdata` and `colorama`; original `.venv` remains unchanged. Added `.env.example` without reading or replacing `.env`.
- Tooling: Added source capture, host metadata inspection, local consolidation/restore, isolated local/Linux regression runners, and synthetic migration rehearsal. Extended the baseline checker with explicit packaged assets and known migration-marker metadata. Source filtering initially omitted required packaged data; the filter was corrected and a complete new capture was verified before successful regression evaluation. Earlier incomplete/interrupted runs are diagnostic attempts, not pass evidence.
- Verification: Complete-source Linux/Python 3.12.3 suite **565 tests passed in 564.162 seconds**. Ran with the server's existing dependency environment, synthetic providers, external network/DNS blocked, credentials excluded, and disposable tmpfs test state. This is not a power-loss durability test. Local focused Windows conversation test passed. JavaScript live-refresh test: **one passed**. Tooling tests: **16 passed**, including private-value exclusion, read-only schema inspection, migration-metadata allowlisting, archive validation, asset inclusion, offline-run isolation, source backup/restore, and refusal to overwrite later owner edits. `pip check` reports no broken requirements.
- Migration evidence: Seeded a synthetic project/task with older local code; initialized current team, milestone, assurance, and organisation stores twice; verified unchanged legacy rows, used-call count, limits, review note, and output bytes; older code read those same records successfully afterward. Real accounting, permission, authentication, and complete artifact-history rollback remain unverified.
- Files and artifacts: Root `superhuman/`, `source-provenance.json`, dependency files, `.env.example`, `.gitattributes`, `.gitignore`, root README, this roadmap, `tools/`, and `tests/`. Local ignored evidence: `baseline-server.json`, `baseline-server-host.json`, `.workforce/linux-baseline-regressions.log`, `.workforce/migration-rehearsal.log`, source capture/provenance, and consolidation backup receipt.
- Production effects: No production source, database records, credentials, permissions, spending limits, activation settings, or services changed. Remote tests used only disposable temporary state; no provider requests were made by this work.
- Status: WF01 remains In progress with its integrated-check item satisfied; WF14 moved to In progress for the offline harness only. No live or business-quality acceptance is claimed. Remaining WF01 checks, objective lifecycle/allowance enforcement, independent review extensions, concurrency enablement, and owner-approved live evaluation thresholds remain open.
- Next action: Implement WF02 objective identity and cumulative allowances using the recorded mapping, with initial sequential dispatch and migration tests that preserve existing permissions, spending reservations, and task history. Broader external workflows and release acceptance still depend on their recorded authority and evaluation decisions.

### UP003 — 18 October 2026 Initial persistent objectives and shared execution allowances

- Related requirements: WF02; owner controls under WF13; sequential boundaries under WF05; evaluation harness under WF14.
- Changes: Added `superhuman/team/objectives.py`; integrated it with `team/store.py`, `team/budget.py`, `team/work.py`, `team/engine.py`, `team/web.py`, and the agentic tool/engine boundary. Added `tests/test_workforce_objectives.py`; extended `tools/run_workforce_remote_checks.py` with explicit candidate manifests and extra integration modules. Updated README and this roadmap.
- Records: Four additive tables (`workforce_objectives`, `workforce_objective_tasks`, `workforce_objective_plans`, `workforce_objective_costs`). New cost rows retain their existing canonical `team_costs` identity and integer-microdollar accounting. Objectives bind an eligible unstarted root task, its future child handoffs, source conversation/turn where present, exact initial brief, criteria, lead, versioned plans, deadline, and cumulative allowances. A conversation collection or business project is not silently treated as one objective.
- Enforcement: Objective identity is inherited atomically by real handoffs. Non-owner creation cannot escape into untracked work in an objective-managed project; scoped coordinator decisions cannot target other objectives, and managed work/signals are excluded from the shared coordinator. Existing task, project, employee, source, exact-model, pool, and global-budget controls remain in force.
- Spending/attempts: Reserve aggregate dollars and request attempts inside the existing `BEGIN IMMEDIATE` cost-reservation transaction, before provider execution. Count objective-scoped Twin coordination/review, specialist decisions, and paid draft/research subcalls against the same objective, across budget periods. Unknown reservations survive recovery; explicit reconciliation can change verified dollar totals but does not reset recorded attempts. Local preparation failures proven to precede invocation release dollars only. Recheck current controls immediately before invocation and each tool action; preserve in-flight receipts after pause/cancel.
- Sequential execution: Transactional dispatch checks reject a second dispatched/running assignment in the same objective, and reservation checks reject simultaneous provider requests. This does not enable parallel workforce execution or waive the concurrency gate.
- Revisions/state: Formal output-review rejection and permitted pre-execution brief changes share one revision allowance. Plan changes retain history and an impact note. Allowance amendments are versioned owner decisions over totals from original creation; consumption, reservations, revisions and the original start time survive restart, pause/resume and amendments. Zero revision rounds permits initial execution, not revisions. Post-start alternatives and conversation brief replacements are refused until a versioned impact workflow exists.
- Owner experience: An unstarted ordinary task offers objective enrollment with explicit dollar/request/time/revision fields and a rationale. The objective page shows the original source conversation when present, linked assignments, actual/reserved usage, outstanding accounting, current brief, plan history, allowance changes, pause/resume/cancel, and owner final acceptance. Completion requires all assignments accepted, current artifacts/evidence rechecked, accounting settled, disputes/handoffs resolved, and a recorded owner criteria attestation. It does not fabricate outcome measurements or independent factual verification.
- Compatibility: No existing assignments or spending are silently enrolled. Initialization is additive/idempotent. The populated migration test preserves every pre-existing table row, including custom employee permissions, owner grants, uncertain spending, rates, settings and audit history, across repeated initialization. Prior-run/spend/handoff enrollment is refused. No new dependencies, scheduler, provider, external tool grant, live data migration or deployment were introduced.
- Verification: **47 local tests passed in 23.215 seconds** (31 objective integration tests and 16 existing tooling tests). Coverage includes exact conversation origin, fresh-process persistence, nested scope inheritance, real handoff acceptance, shared root/child consumption, concurrent last-request reservations, pre-provider dollar refusal, uncertainty/recovery/reconciliation, pause/cancel/deadline controls, project pause, pre-invocation and pre-tool revocation, sequential dispatch, owner revision limits, immutable initial plan history, scoped coordinator/review billing, idle-cache behavior, cross-objective refusal, source/permission/history migration preservation, artifact tampering, blocked asynchronous work/active alternatives, and authentication/CSRF for owner routes.
- Final candidate identity: 240 application source/asset files; fingerprint `0471ea6068a82b484d0ae7c9bb0ba422bf65d18fc17b8346ac787d89f959971b`. `source-provenance.json` intentionally retains the historical v1.41 baseline; the candidate manifest records the eight changed/added application paths. Final Linux validation runs against this exact snapshot with fixture providers and external networking blocked. Earlier candidate/interrupted runs are retained as development evidence, not substituted for final-snapshot acceptance.
- Final Linux verification: **565 existing regressions passed in 623.138 seconds; all 31 new objective integration tests passed in 11.242 seconds**, against the exact candidate fingerprint above on Python 3.12.3. The runner exited successfully and post-run hash verification confirmed all 240 application files still matched the tested snapshot. Tests used fixture providers, cleared credentials, blocked external networking, and disposable tmpfs state; no production application records or services were changed. The local 47-test suite overlaps the Linux objective checks; these counts are not additive.
- Evidence artifacts (local, ignored): `.workforce/objective-tests-final.log`, `.workforce/objective-linux-final-complete.log`, `.workforce/objective-linux-final-complete.manifest.json`. Python syntax and `git diff --check` also pass. Earlier candidate and interrupted runs are diagnostic history, not final pass evidence.
- Limitations/status: WF02 and WF13 remain In progress. Milestone migration, material changes after execution starts, autonomous versioned graph replanning, independent-review extensions, outcome follow-up, reviewed deployment/rollback packaging, owner-approved quality thresholds and live provider evaluations remain open. No business or production readiness is asserted. Production services, configuration, credentials, business records, permissions and budgets were not changed.
- Next action: Complete WF03/WF05 impact propagation and milestone enrollment against explicit migration and authority contracts; retain these counters and historical links through every subsequent phase.

```text
Update ID:
Date:
Related requirement IDs:
Summary of changes:
Files or commits:
Migration or configuration effects:
Verification performed:
Results and evidence:
Remaining limitations:
Backlog status changes:
Next action:
```

## 15. Acceptance evidence register

| Evidence ID | Requirement | Version or commit | Scenario and environment | Result | Artifact or run reference | Reviewer and date |
| --- | --- | --- | --- | --- | --- | --- |
| E001 | WF01 partial: local inventory tooling | Checkout base `26e3fbb`; source fingerprint in UP001 | Local Windows / Python 3.13.0; four isolated tests and read-only schema inventory | Tooling tests pass; consolidated application and live behavior unverified | `tools/workforce_baseline.py`, `tests/test_workforce_baseline.py`, local ignored `baseline-local.json`; commands in UP001 | Implementing agent, 18 October 2026; no independent acceptance review |
| E002 | WF01 integrated baseline; WF14 offline harness only | v1.41 source markers; fingerprint in UP002 and `source-provenance.json` | Complete captured application, Linux/Python 3.12.3; isolated fixture state and blocked external network | 565 regressions pass; one JS check and 16 tooling tests pass; synthetic migration/readback passes. Live quality and complete real-data recovery unverified | UP002; `.workforce/linux-baseline-regressions.log`, `.workforce/migration-rehearsal.log`, `.workforce/local-before-v141/consolidation.json`; runners under `tools/` | Implementing agent, 18 October 2026; no independent business acceptance review |
| E003 | WF02 initial ordinary-assignment scope; WF13 owner controls; WF14 regression extension | Unreleased local candidate; fingerprint in UP003 | Windows/Python 3.13.0 focused suite; Linux/Python 3.12.3 final isolated candidate suite | 565 existing regressions and 31 new objective integration tests pass on the final Linux snapshot; 47 overlapping local checks pass. Fixture results do not establish live/business acceptance | UP003; `tests/test_workforce_objectives.py`; candidate logs/manifest listed above | Implementing agent, 18 October 2026; no independent business acceptance review |

## 16. Code references for the initial evaluation

These are workspace-relative implementation references. Consolidation under WF01 should update them to authoritative source paths while preserving this historical context.

After UP002, the authoritative local implementation is `superhuman/`; `source-provenance.json` records its server baseline. Current modules include `superhuman/agentic/`, `superhuman/conversationwork/`, `superhuman/team/`, `superhuman/milestones/`, `superhuman/assurance/`, `superhuman/organisation/`, and `superhuman/foundation/`. The package paths below remain the historical references from the initial review, not alternate places to implement new behavior.

| Area | Reference |
| --- | --- |
| Base runtime | `superhuman/runtime/engine.py` |
| Base project execution | `superhuman/projects/engine.py` |
| Agent decisions and tools | `superhuman-v1.41-upgrade/payload/agentic/engine.py` and `tools.py` |
| Conversation execution | `superhuman-v1.41-upgrade/payload/conversationwork/execution.py` and `bridge.py` |
| Specialist ownership and handoffs | `superhuman-v1.41-upgrade/payload/team/store.py` and `work.py` |
| Twin coordination | `superhuman-v1.26-upgrade/superhuman/team/engine.py`, with later package transformations |
| Milestone coordination | `superhuman-v1.39-upgrade/payload/milestones/engine.py` |
| Group discussions | `superhuman-v1.36-upgrade/superhuman/teamhub/engine.py` |
| Storage retrieval | `superhuman-v1.30-upgrade/superhuman/foundation/storage.py`, with later access-control changes |
| Proactive signals | `superhuman-v1.30-upgrade/superhuman/foundation/proactive.py` |
| Evidence and outcomes | `superhuman-v1.32-upgrade/superhuman/assurance/` |
| Shared organisational context | `superhuman-v1.40-upgrade/README.md` and `superhuman-v1.41-upgrade/payload/organisation/context.py` |
| Latest package installation | `superhuman-v1.41-upgrade/install_v141.py` |
| Packaged validation and remaining live checks | `superhuman-v1.41-upgrade/VALIDATION.md` and `LIVE-ACCEPTANCE.md` |

