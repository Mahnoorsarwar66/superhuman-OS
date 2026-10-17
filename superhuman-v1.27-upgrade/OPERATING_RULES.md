# Connected Twin operating rules

## One Twin, two kinds of work

The organisation remains eight identities: Mahnoor Twin and seven specialists. The same Twin uses your confirmed preferences and current owner updates for internal coordination and communications assistance. A communications analysis is a bounded job, not another employee. Source messages cannot become owner instructions, confirmed memories or executable department tasks by themselves.

Use Talk → Mahnoor Twin for views, limitations, priorities and temporary constraints. Use Talk → Personal assistant for communications intake, scheduled briefs, urgent-item proposals, draft replies and sharing decisions. The Twin's conversation page links to the assistant and its latest completed overview. Existing inbox reports remain available separately.

## Reading, model consent and private sharing

Each connection has separate reading and model-processing controls. Connecting it grants neither. Enabling reading can cache private previews; enabling model processing permits bounded, recognised-secret-masked excerpts from those previews to be sent to your configured model. Common secret masking is best effort, not complete data-loss prevention. Message previews and analysis artifacts remain private local database records; connector credentials are encrypted separately with the existing external key.

Gmail/Titan reading remains with the original read-only connector; the assistant bridge does not mark messages read, send mail or create duplicate remote readers. Its coverage uses the original provider sync time so copying old previews cannot appear to be a fresh remote check. Credential rotations require relinking the assistant to the matching inbox generation.

Slack reads only explicitly selected conversation IDs, with at most ten selected conversations per workspace and fifteen messages per page. It uses persistent fixed page windows/cursors, one workspace read per at least 61 seconds and server Retry-After deferral. The initial scan and discovered-thread follow-up cover seven days; at most 100 recent discovered threads are followed. This is a bounded poller, not a comprehensive Slack event archive. Old/undiscovered threads, inaccessible DMs, unrefetched edits, deleted history and file contents can be absent. Permission/continuation errors remain visible rather than silently advancing past a missing page.

WhatsApp intake accepts signed webhook messages for the configured Business number. It does not connect WhatsApp Web, retrieve personal chat history or download media. It never treats a URL verification challenge alone as proof of successful message delivery. Confirm a real signed message after configuration.

Source identity deduplicates repeat provider deliveries. Re-fetched changed content retains its source ID but changes its fingerprint/version, invalidating stale drafts and sharing decisions. Within a batch, identical text is labelled as a possible duplicate; separate channels remain separately attributed and are not silently merged. Archived previews remain retained records, are excluded from model selection, and free active-preview capacity. At 2,000 unarchived previews per connection, reads stop advancing until capacity is addressed; this is backpressure, not a complete archive.

## Drafts and department work

The Twin can create local reply drafts. Review the original full conversation, verify the recipient and copy the draft into the original app to send it yourself. There are no outbound messaging API methods in this release. Saving or editing a draft does not send anything or grant standing external-action authority.

Specialist proposals stay proposed until you approve private sharing with a specific destination project and a recorded rationale. The destination must be active, restricted and graded consequential or high risk. Approval creates a single governed Team task for the proposed specialist; it still needs its owner start approval. Source changes prevent reuse of stale proposals. Routine internal Team work retains v1.26's existing delegated-review rules.

New sensitive assignments exclude public-web tools to prevent private source material being included in public research queries. Existing private runs carrying those tools are held. Their owner repair control removes public-web permissions, preserves required tools/evidence and records the inspection rationale. It refuses a repair that would remove a required tool; use a revised private task instead. No source or draft is shared automatically across departments.

## Schedule, costs and recovery

Default briefs are 09:00, 14:00 and 20:30 Asia/Karachi. Times and IANA timezone are editable. They are saved in the app; no Slack/WhatsApp/email delivery or mobile push is configured. A scheduled slot has a unique date/slot key. No earlier slot is backfilled when initially enabling the assistant. After downtime the latest elapsed slot is caught up and older queued slots are marked skipped. Previous-day briefings are not replayed as current updates.

Intake works in batches of up to twelve previews, roughly every ten minutes, subject to the worker, consent, queue and budget. Default daily ceiling is twelve model attempts: three reserved for scheduled briefings and nine shared by intake/manual briefs. A failed attempt counts. The queue admits at most six queued/running jobs, and the existing worker lock permits one bounded step at a time. New source volume can exceed these limits; check pending counts and coverage before assuming the inbox is clear.

All communications analyses use the existing Team model and Twin dollar pool. v1.27 does not create a new $200 period, renew an expired period, reset spending or assume a live model price. v1.26's conservative reservations, uncertain-call accounting and provider reconciliation remain in effect. Hosting, outside subscriptions/platform fees and activity outside this application are not included in that local model ledger. Provider invoices remain the final billing record.

The Twin can propose an urgent in-app item from analysed sources. It does not provide guaranteed emergency monitoring or guaranteed deadline detection. Past reminders, unknown timezones and incomplete previews require checking against the original source. Acknowledging an alert clears its attention state but does not resolve the underlying obligation.

Running analyses are marked interrupted after a restart and are not silently replayed. An explicit owner retry captures fresh context and atomically authorizes a single new job, even if submitted twice. Unknown model usage retains its full dollar reservation. Source, consent and owner-context changes during a request invalidate its output. Private results that completed after a change are held rather than automatically shared. Owner retry is a new paid attempt, not a refund of the old request.

The global worker pause stops pollers and analysis; a still-enabled WhatsApp endpoint can continue caching signed inbound messages. Disable that connection's reading control to stop webhook receipt. Disconnect removes this connector credential and future reading consent while preserving saved records. Revoke remote grants/subscriptions separately where desired. Reconnecting requires explicit renewed controls.
