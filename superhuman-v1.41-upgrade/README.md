# Superhuman OS v1.41 — Ask, execute, return

**Requires v1.40. Install v1.40 first if it is not already installed.** This guarded incremental package preserves the shared foundation added in v1.40.

## The gap this addresses

An employee could discuss a research request but could not turn it into execution from the conversation. This installation connects direct owner messages to the existing governed employee task system and returns the saved output to that same conversation.

For example, in a fresh Katherine conversation:

> Hi Katherine, can you go online to research about the UKVI guidance on the UK Innovator Founder Visa for New Businesses?

The application recognises a direct work request using a structured response and an independent direct-owner intent gate. When the existing controls permit it, it creates a tracked research assignment, queues the worker and shows the actual status. It does not require the owner to approve the same routine request again through a separate task form. A result is shown only after the existing search runner returns API citations and the saved output/evidence checks pass.

## What is connected

- Direct owner conversations with all seven specialists.
- The Twin can route a routine request to a specialist; project-linked conversations retain their approved department/milestone boundaries.
- Public-web research uses the existing cited search runner: one bounded search request per assignment.
- Local drafts use the existing three-call draft, critique and edit pipeline.
- Progress, results, execution evidence, task controls and downloads appear beneath the source conversation message. The existing live refresh updates them and changes the unread signature when the work changes.
- Later conversation turns receive bounded excerpts of actual saved work results and their current status, rather than invented execution claims.
- Ordinary discussion and task suggestions remain available.

## Work organisation and authority

An unlinked direct conversation uses a clearly named department collection such as **Katherine — Conversation work**. This contains bounded one-off owner requests; it is not a new strategic project, an automatically approved milestone plan or a fabricated confirmed project interview.

A linked project uses that actual project. Its pause, risk, privacy, interview, sharing, roster and milestone controls still apply. A milestone project must have one unambiguous working authorised milestone for that specialist. The application will not escape a blocked linked project by creating a different work collection.

Only an explicit current owner message can authorise this path. Coworker discussions, work-card reviews, inbox summaries, quoted instructions, model suggestions and source documents do not gain execution authority. The exact current owner message becomes the work brief; generated titles or acceptance criteria do not authorise additional actions.

Ambiguous work, broader projects and requests depending on unavailable context may still need clarification. This release connects research and local drafting; it does not make every application tool callable from chat.

## Privacy, costs and failures

- Automatic web research uses the exact current public question. Private prior conversation, founder biography, project context and local uploaded source text are excluded from this search path. Private classifications and common sensitive identifiers block automatic public-web execution.
- Existing employee tool grants, team activation, department status, worker pause, project controls, exact-model rates and dollar pools remain enforced. The application never silently changes the model or increases a budget.
- Each new work assignment starts with a **$1 ceiling**, **one research request or three draft requests**, and two local execution/evidence steps. Request recognition and subsequent reviews remain separately metered through the existing conversation/team ledger.
- There can be at most two active new work assignments from one conversation and twelve work requests per hour per conversation. An identical active request is not queued twice.
- Missing citations, provider failures, uncertain usage and failed final checks hold the work. There are no automatic paid retries in this bridge. Inspect the task and retained evidence before cancelling or making a fresh explicit request. Raising a ceiling alone does not authorise replay of an uncertain prior tool call.
- Results remain reviewable; citations and integrity checks do not prove factual correctness or endorse a strategic decision.
- Archiving a conversation does not cancel an assignment you already requested. Use its task pause/cancel controls.

No external messages, publishing, submissions, purchases, shell actions or new source permissions are enabled.

## Install

Extract the ZIP into `C:\superhuman-os-starter`. Check that it creates `C:\superhuman-os-starter\superhuman-v1.41-upgrade\upgrade_server.sh` without an extra nested folder.

Windows PowerShell:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.41-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

Then, in the Ubuntu SSH window:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.41-upgrade
bash /home/superhuman/superhuman-v1.41-upgrade/upgrade_server.sh
```

The launcher selects the installed app directory, checks recognised source and service ownership, stops services, takes a private backup, runs staged offline regressions, installs and restarts. Existing activation, permission settings and budgets are retained. Installation itself makes no paid model or search request.

## First live check

Confirm version 1.41.0, open a fresh Katherine conversation and send the original question above. A pass requires a linked task, actual execution evidence, a cited saved result returned to the conversation and a corresponding cost record. A queue acknowledgement alone is not a pass.

If it is blocked, use the specific reason and linked controls. A configured model/rate card does not establish live hosted-search compatibility; an actual provider request is still necessary to verify that. Do not rely on the full endorsement assignment until the real search and guide-reading workflows are tested.

## Rollback

Use the exact backup path printed by installation:

```bash
bash /home/superhuman/superhuman-v1.41-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.41-EXACT_TIMESTAMP
```

Rollback restores v1.40 source and retains business records, memory, spending and evidence. The worker remains stopped/paused, and unfinished conversation-created assignments are paused so older code cannot automatically plan or replay them. Inspect those assignments before any manual resume. Owner source edits after installation cause rollback to refuse rather than overwrite them.
