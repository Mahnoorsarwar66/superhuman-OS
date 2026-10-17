# Team operating model

## Authority and priorities

Mahnoor owns priorities, approval policy, sensitive decisions, spending and final authority. The Twin coordinates the seven specialists. Each task has a single accountable specialist and a canonical execution record. A task belongs to an owner-created project with objective and acceptance criteria; creating an empty active project lets the Twin propose its first task.

P0 is owner-reserved critical work; P1 is high, P2 normal, P3 low, P4 backlog. The Twin can move a task at most one level from its project's priority without assigning P0 or changing a P0 project. The scheduler also considers due dates and age. Project controls establish minimum risk and sensitivity; task overrides can strengthen them. Changes revoke previous start grants.

Routine internal work can start and receive a Twin review without an individual approval. Consequential and high-risk work, restricted information, and sensitive prerequisite sharing across departments require owner approval. Confidential/restricted handoff requests require an explicit owner decision. Prerequisite classification cannot exceed destination controls. An approved prerequisite artifact must remain readable and hash-valid before the dependent run advances.

The Twin can request at most two routine revisions before owner intervention. It must see a complete deliverable of at most 12,000 characters and verified action evidence before approving. Longer outputs require owner review. Evidence verification checks saved tool outcomes and artifact integrity; it does not prove every substantive claim is true.

Specialists use team.handoff, team.challenge and team.remember. Handoffs create owned child tasks, pause the parent and return approved results as bounded excerpts. Chains are limited to three nested handoffs. A challenge pauses the task. The Twin may maintain its instruction or escalate; it cannot approve the specialist's contrary alternative. You can authorize that alternative with a recorded rationale.

## Twin conversation and memory

Talk → Mahnoor Twin is the internal owner update channel. Record instructions, decisions, priority changes, preferences and temporary constraints. Temporary constraints require an expiry. The Twin responds when the worker processes the update; this is not yet an external inbox or messaging assistant. Begin with frequent short check-ins while calibrating charters and preferences.

Each employee sees its own confirmed memory and permitted shared memory, filtered by assignment sensitivity. Twin-private memory stays with the Twin. Confidential/restricted material cannot be confirmed as shared memory. Employee/Twin proposals are not lasting facts until you confirm them. Writing skills are versioned instructions plus owner-approved examples; no model weights are fine-tuned and no undocumented automatic training is claimed.

## Persistence and limits

Identity, queue, projects, handoffs, messages, memory, writing skills, decisions and costs live in the existing local application database. The existing worker schedules bounded steps. The Twin wakes on meaningful changes, with a five-second decision interval and a 30-cycle rolling hourly ceiling; it does not repeatedly ask the model about an unchanged queue. These are ceilings, not guaranteed throughput. Existing worker/department policy gates remain in force. Default task limits are 12 model requests, 16 steps and $5 of recorded charges/reservations. You can explicitly adjust them on the task page.

In-flight Twin decisions are held after restart rather than automatically replayed. In-flight model reservations remain uncertain. Inspect the run, model request record and cost ledger, then use the owner resume/reconciliation controls. Task/employee/project pauses and withdrawn permissions stop subsequent steps; they cannot undo a request already sent to the provider.

Legacy jobs remain accessible and are not automatically adopted into the new team. Eligible single-task agent runs can be adopted explicitly. Existing Writer history remains; new team projects cannot use Writer as an employee, and legacy Writer jobs are held while the team is enabled. v1.25 supervision remains available when the team is off; when enabled, the Twin takes over its coordination slot rather than running a second competing supervisor.

## Dollar accounting

Before a model call the app atomically reserves dollars against the total, its Twin/staff pool, hosted-tool pool and the task ceiling. Text input is conservatively estimated from serialized bytes with overhead; output is bounded, and hosted web search reserves additional input and a tool-call allowance. Model cards are owner-confirmed exact identifiers. Unrecognised options/models fail closed after the budget is configured. SDK automatic retries are disabled on application-owned clients.

Returned token usage settles the text estimate at pinned input/output rates, including reported output reasoning tokens. Cached tokens are conservatively counted at the full input rate. A bounded hosted-search call is conservatively charged up to $0.025 in the local ledger. Unknown usage/provider failures retain the full reservation. Charges exceeding a reservation hold further paid work. Release reserve or reconcile with provider evidence before clearing a hold. The $40 reserve is unavailable until you explicitly allocate it.

The ledger is an application estimate and admission control, not an exact provider invoice or guaranteed provider-side $200 hard cap. Provider usage, pricing, search billing and outside activity can differ. Set provider-side controls where available and reconcile the provider dashboard, especially during the pilot. ROI evaluation should combine completed approved work, usefulness/time saved and provider invoices; v1.26 does not claim an automatic ROI measurement system.

## Installation 2: v1.27

Connect selected communication accounts, build shared intake and deduplication, assign personal-assistant work to the Twin, and add morning/midday/evening briefings and urgent exceptions. Connector access, recipients and read/draft/send permissions will be defined per channel. Sending messages, submissions, publishing, purchasing and remote account changes are not granted to the v1.26 team. Confirm channel availability and authentication during that installation; no connection is implied by this package.
