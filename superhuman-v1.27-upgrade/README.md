# Superhuman OS v1.27 — Connected Twin & Communications

Installation 2 of the agreed two-installation programme. Requires a successfully installed v1.26. This package extends the existing Mahnoor Twin; the organisation remains one Twin and seven specialists.

| Capability | What this package does |
| --- | --- |
| Email | Reuses existing Gmail/Titan read-only connectors and bridges selected saved previews into the Twin inbox |
| Slack | Reads explicitly selected conversations with persistent pagination, rate handling and recent discovered-thread follow-up |
| WhatsApp | Receives signed text webhooks for a configured WhatsApp Business number |
| Personal assistant | Triages opted-in previews, proposes urgent items, prepares local reply drafts and suggests specialist work |
| Briefings | Saves morning, midday and evening briefs in Superhuman; default 09:00 / 14:00 / 20:30 Asia/Karachi |
| Governance | Separate reading/model consent, source provenance, owner-approved private sharing and the existing USD budget |

Start at **Talk → Personal assistant**. Update your current views and constraints at **Talk → Mahnoor Twin**. Reply drafts stay local: review the full conversation and recipient in the original app before sending yourself. This release has no outbound messaging methods, automatic submissions or purchases.

Connections start paused, model processing starts off, and the assistant starts disabled. No credentials are bundled. Install first, then follow CONNECTION_GUIDE.md and explicitly enable selected channels and the schedule.

WhatsApp Business intake does not expose personal WhatsApp history. Media and attachments are not fetched. Slack/email coverage is bounded; this is not a complete archive or guaranteed urgent-message monitor. Briefings and alerts appear in the app; external push/email/WhatsApp delivery is not enabled.

INSTALLATION_GUIDE.md contains exact Windows/Ubuntu commands and rollback instructions. OPERATING_RULES.md explains workflow and limits. TESTING.md records local verification and the remaining live checks. No new server dependency, service unit or Nginx configuration is installed.
