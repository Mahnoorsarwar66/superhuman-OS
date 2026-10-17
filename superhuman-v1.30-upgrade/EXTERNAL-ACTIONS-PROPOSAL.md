# External actions: proposal for Mahnoor's review

This document proposes the next permission model. v1.30 does not enable sending, submissions, purchases, publishing, remote account changes or new external tools.

## Recommended model

Give The Twin standing mandates, rather than asking Mahnoor to approve every routine action. Each mandate names the action, responsible agent, connected account, recipients or audience, permitted information, limits, expiry and escalation conditions. Agents can operate autonomously inside a mandate; anything outside it needs an owner decision. The Twin cannot expand a mandate herself.

| Action class | Proposed autonomy | Examples |
| --- | --- | --- |
| Read and prepare | Automatic within existing consent and task controls | Read selected channels, research public information, draft replies, prepare documents, identify meeting times |
| Routine external action covered by an owner-approved mandate | Automatic after identity, content and limit checks | Schedule internal meetings within agreed hours; send an approved follow-up template to a verified existing contact; update selected CRM fields; open a draft pull request |
| Consequential action or exception | Specific owner approval | Submit applications, publish new public claims, send sensitive material, accept terms, enter commitments, make payments, merge or deploy code, change account permissions |

Routine approval should be reusable only within a clear mandate, rather than a blanket approval for a channel. A general request to help with email does not authorize sending every kind of message.

## Department responsibilities

- The specialist prepares the proposed action and checks its domain requirements.
- The Twin coordinates timing, priorities and cross-department consistency. She can approve routine actions only within an owner-approved mandate.
- The execution adapter validates the mandate independently before acting; a model's assertion that it has permission is insufficient.
- Mahnoor decides exceptions, sensitive or high-risk actions, and any expansion of authority. A specialist cannot bypass The Twin.

## Mandate example for review

“Sarah may send one follow-up using this approved template to contacts already on the verified university-pilot list, from this connected account, after five working days without a reply. Maximum five per day and one per contact per week. No attachments, new product claims, prices or commitments. Stop and ask The Twin when the contact replies. Expires after 30 days.”

This is an example only; it is not an activated permission.

## Execution requirements

1. Verify the correct recipient and account; do not infer identity from a first name or untrusted message.
2. Build a concrete action with a preview, source references, project link and mandate identifier.
3. Check sensitivity, attachments, content constraints, current mandate version, expiry, rate and spending limits.
4. Recheck authorization immediately before execution, especially after edits or a delay.
5. Execute with a unique action identifier to prevent duplicates. For an uncertain response, inspect provider state before retrying; never blindly resend.
6. Record the provider receipt and actual outcome. An attempted action is not a completed action.
7. Notify Mahnoor according to urgency and retain an activity record. Provide correction or cancellation where the provider supports it.

## Build order after approval

1. Permission records, action previews, audit trail, pause/revoke controls and provider adapters in a dry-run mode.
2. One useful reversible integration, such as internal calendar scheduling, with a narrow mandate and real provider verification.
3. A verified-contact outreach workflow using approved templates and strict caps.
4. Additional departmental actions only after the first integrations demonstrate reliable behaviour.

## Decisions to review later

- Which account and action should be the first integration?
- Which actions can The Twin authorize under standing rules, and which always require Mahnoor?
- Which recipients are eligible for automatic contact?
- What information, daily limits, quiet hours and mandate duration should apply?

No answer to this proposal is needed to install v1.30.
