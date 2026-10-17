# Superhuman OS v1.39 — Team execution reliability

Upgrade from the installed v1.38.0. This package addresses the full-team live QA findings, including the earlier archived-conversation retry issue. It changes execution/review behavior and clarity; it does not introduce another feature area.

## Included repairs

- **Action contracts (SH-19):** new model requests use typed argument objects instead of JSON embedded in a string. Saved/legacy action responses remain readable. Empty legacy finish arguments are accepted only for finish; tool contracts, real evidence IDs, allowed tools and output checks remain mandatory. Invalid actions stop within the existing limits.
- **Grounded draft review (SH-20):** the reviewer selects exact program-provided requirement identifiers. Evidence quotes must still occur in the actual draft; only whitespace and typographic quote normalization is tolerated. Invented requirements/evidence remain blocked. The assigned task's acceptance criteria are explicitly supplied to the draft tool. The existing three-request draft/review/edit allowance is retained.
- **Lead stage decisions (SH-21):** ready contribution, integration and Twin-review stages receive explicit current responsibility and stage-specific actions. A ready review cannot return Wait for a downstream review; the lead must accept, revise or escalate. Nonconforming responses hold for inspection, never approve work automatically.
- **Recovery (SH-22):** the execution page resumes its owning task through one version-checked transaction. A failed transaction rolls back both states. Pausing the parent project, risk requirements, tool withdrawal and remaining allowances still prevent execution. Held-task retries require an inspection note.
- **Exact final output (SH-23):** execution evidence stays in separate metadata/review disclosure rather than being appended to the requested deliverable. The exact final text is checked before handoff. Saved punctuation preferences are applied consistently, including ASCII dash separators; numeric ranges are not rewritten. Assignment-specific limits govern a milestone output rather than unrelated milestones' word limits.
- **Status clarity (SH-24):** held assignments and ready contribution reviews become the next step, with the correct responsible actor and a direct link. Project pauses are identified before the brief-confirmation message. Review pages surface runtime/contribution blockers rather than saying there is nothing to do.
- **Artifact labels (SH-25):** failed actions no longer advertise an unusable verified-download link. The saved failure/observation remains inspectable; failed review output is not promoted to successful evidence.
- **Actual lead (SH-04 residual):** newly generated generic contributor instructions use the saved lead's name, including James in Product projects, rather than Katherine. Historical saved instructions are retained; the existing milestone context identifies the actual lead.
- **Model provenance observation:** new collaboration records identify the configured model actually selected for governed billing, with the originally requested model retained separately. Old generation records are not rewritten.
- **Archived retry and refresh (SH-18 / refresh observation):** archived conversations do not offer a retry; polling cannot re-enable archived send. Reply allowance and latest saved context update as replies complete while preserving unsent drafts and active context/proposal edits.

No database migration, new dependency, credential change or service-definition change is required. Existing portraits, records, budgets, tools, global Team activation and project pauses are retained. Installation does not resume held runs, approve outputs, increase allowances or grant external actions.

## Install

Extract `superhuman-v1.39-upgrade.zip` into `C:\superhuman-os-starter`. Confirm the following file exists:

`C:\superhuman-os-starter\superhuman-v1.39-upgrade\upgrade_server.sh`

Run these in **Windows PowerShell**:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.39-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

Then, in the **Ubuntu SSH window** (the prompt begins `root@ubuntu...`), run:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.39-upgrade
bash /home/superhuman/superhuman-v1.39-upgrade/upgrade_server.sh
```

The launcher recognizes v1.38 source, stops the existing services, creates a private data backup, runs staged synthetic regression checks, installs the verified payload, and restarts the services. Allow several minutes for the checks. Existing active work remains subject to its prior controls; the installer does not change global Team activation.

If it reports **Unrecognised v1.38 source**, stop and share the filename/error. Do not bypass the guard or manually overwrite files.

## After installation

1. Hard-refresh the portal; System baseline and health diagnostics should show **1.39.0**.
2. Keep the retained full-team QA project paused until the next observed test. The package deliberately preserves its failed actions and partial outputs.
3. Use a fresh consistent synthetic brief for the next complete run (local drafting explicitly allowed; external actions excluded), with the same eight roles and M1 → M2 dependency. Do not reuse the ambiguous original “no tools” objective as the governing test brief.
4. Inspect the retained held run pages to verify coherent task-aware continuation, but do not bulk-resume them. Some old runs have only two requests left; an upgrade does not increase those allowances.
5. Follow `LIVE-ACCEPTANCE.md`. A synthetic-provider test pass is not a live product-quality sign-off.

## Rollback

Use the exact backup path printed by the installer:

```bash
bash /home/superhuman/superhuman-v1.39-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.39-EXACT_TIMESTAMP
```

Rollback restores exact v1.38 code, removes the newly added action-contract module, and retains records, outputs and accounting. Owner-edited installed files or altered backups cause refusal. The worker remains stopped and paused for inspection; no automatic replay or database restore occurs.
