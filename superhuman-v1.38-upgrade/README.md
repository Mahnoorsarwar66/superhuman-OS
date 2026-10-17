# Superhuman OS v1.38 — Live QA repairs

Install over the installed **v1.37** application. One installation addresses the confirmed conversation, readiness and status-filter findings from the live review.

## What changes

- **Project Conversations:** shows the project's Team channel, milestone discussion threads and separate project rooms together. Archived channels remain discoverable. Other projects' channels and the internal worker conversations behind individual contributions are excluded. Earlier project-conversation URLs use the same renderer.
- **Blocked discussions:** Send is disabled with an explanation when Team coordination, a hold, worker pause, project status, sharing, model-rate configuration, recipient pause or channel allowance prevents the selected request. The server rechecks the applicable controls inside the enqueue transaction. Retry uses the same guard. Request-specific dollar reservations remain a separate check before provider dispatch.
- **Existing queue:** a saved queued round displays “Waiting for activation / controls” when controls prevent dispatch. Its saved message is retained and cancellation remains available. Stopped requests do not offer a retry while blocked. No existing discussion is silently retried or deleted.
- **Readiness language:** baseline, employee management and Twin profile distinguish task controls from worker connectivity. Connected does not imply that a specialist has completed an assignment. Team holds and worker pause appear in global readiness.
- **Project status:** one Complete filter includes both completed governed projects and approved earlier projects. Older `state=approved` bookmarks use the combined view.
- **Live refresh:** discussion readiness and the Send state update together while preserving the local message draft.

This release changes 15 source/asset paths. It adds no employee, budget, model, document grant, or global execution permission. It preserves the previously verified portraits, exports, calendar conversion, interview prefill and quality-check repairs.

## Install

Extract the ZIP into `C:\superhuman-os-starter` so this file exists:

`C:\superhuman-os-starter\superhuman-v1.38-upgrade\upgrade_server.sh`

Run these in **Windows PowerShell**:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.38-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

Then run these in the **Ubuntu SSH window**, where the prompt starts `root@ubuntu...`:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.38-upgrade
bash /home/superhuman/superhuman-v1.38-upgrade/upgrade_server.sh
```

The launcher checks the existing service accounts and recognized v1.37 source, stops the web/worker services, creates a private data backup, runs staged synthetic regression checks, installs the verified payload and restarts the existing services. Allow the test run to finish. No dependency, Nginx or service-definition change is required.

Existing active work can resume after the service restart under its existing controls. The installer does not enable Team coordination or change the worker's saved pause setting.

If it says **Unrecognised v1.37 source**, stop and share the filename/error. Do not bypass the guard or copy payload files over manually.

## Verify after installation

1. Hard refresh the portal. System baseline should report **1.38.0**.
2. Open the retained Cedar QA project → Conversations. Its channel and M1 discussion should appear, even though the test discussion is cancelled. Another project's channel must not appear.
3. With Team coordination still disabled, open that topic. The readiness panel should explain the blockers and Send should be disabled. A stopped discussion should not offer a paid retry while blocked. Separate direct chats retain their existing budget-gated behavior.
4. Compare System baseline, the Twin employee profile and Sarah's management page. Readiness should describe execution controls; worker status should describe connectivity.
5. Open Projects → Status. Complete should appear once. It includes both completed project types.

## Remaining live acceptance

The completed package tests use synthetic providers. They do not prove that the live agents can research, critically review and produce an endorsement-quality milestone packet.

Use `LIVE-ACCEPTANCE.md` before the next paid run. This installation deliberately leaves autonomous coordination disabled if it is currently disabled. It does **not** implement a project-only worker allowlist: the existing worker also handles earlier jobs, direct conversations, communications and supervision. Do not describe enabling global Team coordination as an isolated project test. An inventory and safe isolation decision are still needed before that test.

Existing task-first conversion continues to protect unfinished tasks. This package verifies the retained task links and non-destructive rejection; it does not migrate existing tasks into milestones or cancel useful work automatically.

## Rollback

Use the exact backup printed by the installer:

```bash
bash /home/superhuman/superhuman-v1.38-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.38-EXACT_TIMESTAMP
```

Rollback restores v1.37 source and retains business records, conversations, approvals, accounting and portrait files. Changed installed files or changed backups cause refusal. The worker remains stopped and paused for inspection; review saved queued discussions before resuming it. No automatic database restore occurs.
