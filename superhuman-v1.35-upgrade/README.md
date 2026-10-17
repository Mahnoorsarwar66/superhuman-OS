# Superhuman OS v1.35 — More depth, simpler conversations

Requires installed v1.34. This is a presentation-focused upgrade over the existing chat, employee and governed project workflows.

## What changes

- Forest-green main navigation returns, with stronger selected states, a deeper Twin welcome panel, more defined surfaces and green header/fact panels. The document and conversation work surfaces remain light and readable.
- Team Conversations uses a Slack-style workspace: a people/project/recent-conversation rail beside the active conversation or conversation list. Direct messages select an employee; project conversations filter exact stored project associations. Search and full-history pagination remain available. New-conversation fields stay in an expandable panel instead of dominating the page.
- A room shows a clear employee portrait/title/context header, readable message rows, the existing live reply status and composer, and expandable suggested-work/conversation controls. Pending cancellation, retries, allowance changes, context correction and governed proposal approval remain available through their existing forms. Typed drafts, dictation and live refresh use the existing backend and scripts.
- Activity uses the same workspace layout around actual recorded employee exchanges. No employee-to-employee dialogue, online status or unread count is invented. A direct conversation still addresses one employee; this release does not introduce a new multi-agent group-chat execution model.
- Employees use a portrait-only wrapper at 128px (120px on narrow layouts); employee profiles use 112px (104px on narrow layouts). The old `ux-avatar:after` bot-face drawing cannot overlay these portraits. The eight v1.34 images are reused unchanged.
- Narrow layouts use a collapsible people/conversation rail. Native links, forms and disclosure controls remain usable without JavaScript. A small enhancement opens the new-conversation disclosure and preserves scroll position while existing live fragments refresh; older-history views do not auto-jump to the bottom.

## How milestone creation currently works

Creating a normal project, including one inside a department, does not automatically create milestones. v1.34 starts its project interview. For a milestone project:

1. Open the project's Manage view and choose Set up milestone leadership / Appoint department lead. The department specialist becomes the lead; The Twin remains supervisor.
2. Open Plan & work and add milestone titles, questions, acceptance criteria, contributors, reviewers and dependencies.
3. Confirm the required brief, criteria, evidence scope, source access and project controls.
4. Start milestones explicitly, or enable ready-milestone starts in the confirmed brief. The Twin then starts existing ready milestones through the established gates; it does not generate or approve their plan.

The existing endorsement blueprint already provides seven predefined milestones with the agreed specialist roster. Use the prepared endorsement project if you want that blueprint. Creating a separate ordinary endorsement-department project does not automatically copy those milestones.

Automatic lead/Twin milestone-plan drafting from the project interview remains a future capability. This UI installation leaves planning and approval authority unchanged.

## Install from Windows

Extract the ZIP so this directory exists:

`C:\superhuman-os-starter\superhuman-v1.35-upgrade`

Run in **Windows PowerShell**:

```powershell
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" -r "C:\superhuman-os-starter\superhuman-v1.35-upgrade" root@167.71.196.20:/home/superhuman/
ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20
```

Once you see the **Ubuntu root prompt**, run:

```bash
chown -R superhuman:superhuman /home/superhuman/superhuman-v1.35-upgrade
bash /home/superhuman/superhuman-v1.35-upgrade/upgrade_server.sh
```

The launcher preflights exact source compatibility, stops the two services, makes a private data bundle, runs staged regression checks and installs the guarded code/assets before restarting services. Existing conversations, project interviews, approvals, models, budgets, channel consent and permissions remain under their existing controls. Allow several minutes for the checks. If source is unrecognised, stop and share the error rather than bypassing the guard.

After success, press **Ctrl + Shift + R** in the app, then open Team > Conversations and Team > Employees. Cache-versioned assets are served locally under the existing authentication boundary.

## Rollback

Use the exact v1.35 backup path printed by the installer:

```bash
bash /home/superhuman/superhuman-v1.35-upgrade/rollback_server.sh /home/superhuman/app/backups/v1.35-TIMESTAMP
```

Rollback restores exact v1.34 integration source, removes only the new Team workspace package, retains business data and existing employee permissions, and leaves the worker paused. It refuses source/hash changes or extra owner-added package files before removal. Inspect before resuming work.

## Verification scope

See VALIDATION.md and ACCEPTANCE-CHECKLIST.md. Local synthetic/mocked tests and native HTML/form checks do not establish live installation, microphone availability or business competence. No fresh real-browser desktop/phone visual evaluation was available in this session; check your actual devices after installation.
