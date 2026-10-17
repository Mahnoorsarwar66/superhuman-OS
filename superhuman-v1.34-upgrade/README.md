# Superhuman OS v1.34 — A team that starts with your expectations

Requires installed v1.33. This installation adds project interviews, owner-confirmed operating context, bounded milestone progression, impact reviews, improved document layouts and a calmer interface with eight illustrated AI employee portraits.

## What is implemented

- New managed projects open a saveable five-view interview: outcome, context/research, working together, success/impact and review. Four essential answers establish the initial brief; deeper unknowns can remain visible. Department-specific questions differ across all seven departments. During assigned work an internal tool can propose up to 30 project-specific follow-up questions, with reasons, for the owner to answer together.
- Answer states distinguish answered, research, recommend, undecided and later. Categories distinguish facts, requirements, constraints, preferences, decisions and unresolved questions. Owner answers are not automatically declared independently verified evidence.
- A confirmed brief enters current employee and milestone lead/Twin context, within the roster and sensitivity ceiling. Draft answers are excluded. Saved changes invalidate confirmation and hold future managed execution. Project-control changes require reconfirmation. Existing packet history is retained; changed brief fingerprints invalidate enrolled-project review scorecards.
- Current projects are not silently enrolled or paused during migration. Use their Summary interview card to enrol them explicitly. New managed projects enrol automatically after setup. Legacy standalone agent runs remain governed by their existing interfaces; adopt/organise them as managed projects to use these interviews.
- The agreed EdSync starting answers can fill unanswered endorsement-interview fields. They label historical materials unconfirmed and leave Q61–67 undecided. No exact date, pilot allocation, independent-review method or workbook scope is invented. The two-day target does not start a deadline clock.
- An opt-in brief control lets The Twin start ready planned milestones, including independent work, through the existing worker. Existing project activation, sharing, budget readiness, hold, employee, dependency, requirement-scope, criteria and source gates still apply. This does not approve predecessor packets or create new strategic milestones. Starts create tasks; existing per-task spending and classification gates govern paid execution.
- Confirmed general operating rules are supplied as task/review instructions and visible in How your team works. Judgment, initiative, communication and writing quality rules remain model instructions; this release does not claim deterministic semantic enforcement, new outbound tools, autonomous market monitoring, model training or proactive message delivery.
- Milestone impact records attach to an exact currently owner-approved packet and digest. Assess six success criteria explicitly; separate readiness, observable outcome and evidence/limitations. Record optional non-overlapping costs and time/rate ranges. No measured outcome is inferred from activity, no causal ROI is claimed, and no hourly value is invented.
- Lifetime project ledger summaries include assignment revisions across budget periods. New milestone coordination calls receive project attribution inside the existing atomic budget reservation. Older unallocated coordination, general Twin overhead and unentered costs remain excluded; uncertain reservations are disclosed. This is partial attribution, not a complete audited cost or a reliable comparable-milestone benchmark yet.
- PDF/Word exports gain native headings, bold text, bullets, up to six-column Markdown tables and page numbering. Unsupported tables retain text. Images, complex Markdown/scripts and final pagination need review. Spreadsheet generation remains the existing CSV-based exporter; financial-model scope is deferred.
- The interface uses a quieter light sidebar, green selected states, more readable headings, softer surfaces, clearer forms and next actions, improved employee cards, a Twin home panel and project expectation prompts. Existing Coding, approval, access and recovery controls remain available.
- Eight fictional, generated portraits ship as private local assets. They identify The Twin, Katherine, Sarah, James, Amelia, Chris, Jose and Sam. They do not depict real people or imply continuous thinking. Optional per-answer dictation uses browser speech support and may use the browser's online service; it starts only on a click. Typed native forms work without JavaScript.

## Install from Windows

Extract the ZIP to `C:\superhuman-os-starter\superhuman-v1.34-upgrade`.

Run in **Windows PowerShell**:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.34-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

Then run in the **Ubuntu SSH session**:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.34-upgrade
bash /home/superhuman/superhuman-v1.34-upgrade/upgrade_server.sh
```

The launcher checks service ownership, runs source preflight, stops both services, creates a private data bundle, runs staged regression checks, installs guarded source, initialises the new records/internal clarification tool, restarts services and captures a local baseline. It preserves configured credentials, models, channel consent and spending ceilings. No live model call is required to install. Allow several minutes for the regression suite.

If preflight rejects a source file, retain the error and stop. Do not bypass the guard or overwrite it manually. An older installed version must be upgraded to v1.33 first.

## After installation

1. Refresh the app. Open Team's employee board to see the portraits and actual saved assignments.
2. Open How your team works from Overview. Q61–67 remain grouped there.
3. For a new project, complete the four essential interview answers, save subsequent steps as useful and review the brief. Confirm it explicitly. Unresolved research questions can remain visible.
4. For the existing endorsement project, use Summary > Set up project interview. In Review brief, Use agreed starting answers fills only unanswered fields. Review every answer; exact dates and missing choices remain open.
5. Choose interview sensitivity and project controls carefully. A higher-classified interview cannot be confirmed into a lower-classified project. Sensitive assignments keep existing public-web restrictions. Source-file access still requires explicit named Storage grants.
6. If desired, enable ready-milestone starts in Brief controls, save, then confirm that version. Project activation, source grants, confirmed requirement scope, budget and worker controls still need to be ready.
7. After an owner-approved milestone, open Milestone impact from the project Summary. Treat unsupported measures as Not assessed. Impact records are owner assessments, not independent certification.

## Rollback

Use the exact backup path printed by the installer:

```bash
bash /home/superhuman/superhuman-v1.34-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.34-TIMESTAMP
```

Rollback refuses changed integration source, altered backups or additional package files. It restores v1.33 source, removes the new internal interview permission and pauses affected runs plus the worker. It retains interview/impact/history records and existing business data. Old v1.33 does not interpret the new brief gates; inspect before resuming work. Reinstallation retains saved answers and does not silently resume retired-tool runs.

## Verification limits

See VALIDATION.md. Local fixture tests and rendered export inspection do not prove live installation, research depth, real provider connectivity, microphone availability, endorsement readiness or business ROI. No new real-browser desktop/mobile evaluation was available in this session; native route/form checks and responsive CSS review are the scope of interface verification.
