SUPERHUMAN v1.11.0 — CONVERSATIONS AND TASK SUGGESTIONS FOR APPROVAL

WHAT THIS ADDS
Talk to Superhuman from the same authenticated phone/laptop interface. Each
conversation belongs to one workstream and stores its messages and replies.
The model can discuss your message, ask clarifying questions and suggest up to
three local draft/research tasks. A suggestion is NEVER an executable task until
you click its Approve task button. Saying "approve" in the chat does not press
that button or queue work. Approval is atomic with canonical project creation,
so repeated submissions of the same approval do not create duplicate projects.

Before approval, edit the complete title and instructions shown on the card.
Kind and workstream are fixed for that suggestion. Approving authorizes its
normal budget and queues execution: local drafts allow up to 3 requests;
public-web research allows 1. Outputs still go through existing quality checks
and owner review. Dismiss unwanted suggestions without model requests. Already
approved work cannot be dismissed from chat; inspect it in its task workspace.
Approval is not a claim of task completion or independent factual verification.

CONVERSATION COST AND EXECUTION
- Creating a conversation, reading history, dismissing a suggestion and saving
  a memory form do not call a model.
- Each sent message explicitly authorizes one model attempt, processed by the
  existing background worker. It can take time when the worker is busy.
- Default conversation limit: 20 reply requests, explicitly adjustable up to
  100 total. Failed/interrupted attempts remain counted. An attempt is reserved
  before execution; early failures may consume a reserved slot without reaching
  the API. Limits are counts, not prices or dollar caps.
- Approved task budgets are additional to the conversation budget.
- At most one outstanding message per conversation. Duplicate sends with the
  same submission key return the original turn. A new send after a failure is
  a new, explicitly authorised attempt; failures are never silently replayed.
- You can cancel a queued message before claim. A running request may be billed
  and cannot be labelled a free cancellation.
- Worker pause also pauses queued replies. The continuous worker alternates
  conversation and project work when both are ready. On restart it marks any
  abandoned running conversation turn Interrupted under the global worker lock.
- The same existing OPENAI_MODEL applies (your server currently uses gpt-5-mini).
  The worker retains max_retries=0 and its existing request timeout.

CONTEXT AND MEMORY
- Relevant confirmed v1.10 notes and legacy task context use the existing
  selector. Sensitive new memory notes are excluded automatically; workstreams
  remain separated. Expiry, genre and context limits still apply.
- The latest six complete prior exchanges are eligible, with a combined history
  budget of 20,000 characters; older/oversize exchanges can be omitted whole.
  Only up to 50 prior turns are inspected. The current message is always included.
  Saved-response details show selected history IDs and memory IDs/versions/hashes.
- Current project summaries for this workstream (latest 12) and recent suggested
  task states (latest 10) are supplied as saved-state context. Artifact contents
  are not read automatically. A status is not evidence that anything was sent.
- Each user message has Save this update to memory. This opens an editable memory
  form; it does not save yet. The note defaults to Proposed, and only explicitly
  confirmed notes become eligible for future tasks. User messages above the
  4000-character memory limit require choosing an excerpt; no silent truncation.
- Conversation history persists as history, not as globally confirmed memory.
  Archiving a note stops fresh retrieval but does not erase text already present
  in previous conversation replies, archived responses or task artifacts.
- This is retrieval and discussion, not model training or automatic learning.
  Do not enter passwords/API keys. Owner messages, private saved replies, context
  traces and model output are all stored in the private canonical project DB.

BOUNDARIES
No conversation browsing or inbox/calendar/Slack/WhatsApp/LinkedIn tools, shell
execution, external sends, applications, purchases, scheduling, push, voice,
streaming, auto-refresh or multi-user isolation are added here. A research TASK
can use its existing public-web research runner only after approval. Conversation
answers have no live research and remain unverified model text. Do not rely on
unsupported factual claims. No messages are seeded from ChatGPT history, private
accounts or prior files by installation.

INSTALL ON THE CURRENT CLOUD SERVER
Do not overwrite cloud data with the old Windows database. The server remains
authoritative. The upgrade contains code and tests only; no keys or private data.

1. Extract the ZIP so the new folder on your LAPTOP is:
   C:\superhuman-os-starter\superhuman-v1.11-upgrade

2. In WINDOWS POWERSHELL (PS C:\...>), upload it:

   scp -r -i "$env:USERPROFILE\.ssh\superhuman_replacement" C:\superhuman-os-starter\superhuman-v1.11-upgrade superhuman@167.71.196.20:/home/superhuman/

3. In WINDOWS POWERSHELL, connect as root:

   ssh -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" root@167.71.196.20

4. Wait for the ROOT SERVER prompt (root@...:~#), then run:

   bash /home/superhuman/superhuman-v1.11-upgrade/upgrade_server.sh

The script stages your installed source, applies narrow AST-guarded patches and
runs included tests with synthetic model responses and temporary databases.
The reference files come from the actual delivered v1.9/v1.10 artifacts, rather
than earlier fixture snapshots. The canonical task-creation functions are also
checked before using their transaction interface. Unexpected source is refused.
No tests use .env or call a live model. If checks pass, the script gracefully
stops web/worker, makes a private consistent source/data backup, reruns checks,
installs four source patches plus superhuman/dialogue, and restarts services.
On a later error it attempts to start the existing services again. It does not
change your owner login, HTTPS origin, Nginx, firewall, systemd configuration,
model settings, credentials, existing projects, memory records or budgets.

Tests can take several minutes on the 1-vCPU server. A current task may also need
to finish before graceful stop. Keep the SSH window open. Do not run two copies
of the installer concurrently. If there is an error, share it before retrying.
A private backup on the same Droplet is not protection against Droplet loss;
copy backups off the Droplet separately. Backups omit .env as before.

When both services show active, open:
https://superhuman.167-71-196-20.sslip.io/talk

Refresh or sign in with your existing owner credentials if required. The Talk
navigation link should now appear. The existing Memory interface stays available.

FIRST LIVE VERIFICATION
A. Create a marketing conversation named University discovery (0 model calls).
   Use a small initial request limit, for example 3, if preferred.
B. Send: "Help me prepare for a university discovery meeting. Suggest one local
   task to create a blank checklist under 100 words, with attendees, workflows,
   obstacles, decision criteria and open questions. Do not invent facts or
   commitments. Keep the task as a suggestion until I approve it."
   This authorizes ONE paid reply attempt. Refresh until it completes.
C. Inspect the proposed task. It must not appear as new executable work yet.
D. Edit/approve ONE local-draft suggestion. This separately authorizes up to
   THREE drafting requests. Open the resulting task, review its output, approve
   only if correct. Do not retry automatically if a quality gate blocks it.
E. On a later reply, test Dismiss without approval. Dismissal must queue no work.
F. Use Save this update to memory on a harmless user message; confirm that it
   opens the editable form and creates nothing until you click Save note.

MANUAL CHECK / INSTALL / ROLLBACK
Only run from the app root as the superhuman user, with services stopped before
actual install or rollback:

   cd /home/superhuman/app
   .venv/bin/python /home/superhuman/superhuman-v1.11-upgrade/install_v111.py --check
   .venv/bin/python /home/superhuman/superhuman-v1.11-upgrade/install_v111.py

The installer prints a backup directory, e.g. app/backups/v1.11-<timestamp>.
To roll back CODE, stop both services as root, then run as the app owner:

   .venv/bin/python /home/superhuman/superhuman-v1.11-upgrade/install_v111.py --rollback /home/superhuman/app/backups/v1.11-REPLACE_WITH_ACTUAL_TIMESTAMP

Start both services afterwards. Rollback refuses changed installed source or
altered backup files. It restores the four previous Python files and removes
the new dialogue package. Existing conversation tables, messages, approvals,
projects and memory remain saved; no database is rolled back or deleted. A task
already approved can still run under the restored worker. Pause/review work
before rollback if that is not intended. Inspect errors rather than deleting data.

No new dependencies are required. An optional Windows source upgrade uses the
same install_v111.py from C:\superhuman-os-starter with the local .venv activated,
after stopping local workers. It does not synchronise cloud conversations or
memory; keep the cloud database authoritative.
