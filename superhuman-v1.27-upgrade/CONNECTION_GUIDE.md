# Connect selected accounts after installation

Connections belong to your deployed Superhuman app. Connecting a ChatGPT plugin does not connect this server application. The package contains no account credentials. Reading and model processing have independent opt-in controls; newly connected accounts have both off.

Use the commands below inside the server's SSH terminal unless a step explicitly says Windows. Tokens/passwords are entered through hidden prompts, not shell arguments or chat. Saved connector credentials use the existing mail encryption key outside the application data directory. Back up that key privately with the data backup; a missing key with existing encrypted credentials must be restored, not replaced.

```bash
cd /home/superhuman/app
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli initialize
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli status
```

## Already connected Gmail or Titan

Use **Personal assistant → Connections & consent → Link an already-connected email inbox**. Choose personal_gmail, edsync_gmail, nextstep_gmail or edsync_titan. CLI equivalent:

```bash
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli link-email personal_gmail
```

Enable the connection's reading control. This bridges saved previews, not a new independent email reader. Use the existing **Inbox** page to request a remote sync or enable automatic email reads. Confirm a recent source and the actual provider last-sync time. Then separately enable Twin model processing. If you rotate/reconnect the underlying email credential, relink the assistant connection to that new generation before continuing. Disconnecting only the assistant link leaves the original email connection intact.

## New Gmail connection

Create your own Google Cloud project, enable Gmail API, configure OAuth consent for your account, and create/download a **Desktop app** OAuth client JSON. Follow Google's current verification and account/admin requirements. The helper requests only `https://www.googleapis.com/auth/gmail.readonly`, verifies the selected account and uses PKCE with a laptop loopback callback. It cannot send, modify or mark messages read. External OAuth apps in Testing can have short-lived refresh grants; use an appropriate approved/published configuration for sustained service, or reconnect when Google expires/revokes a grant.

On Windows, put the downloaded client JSON somewhere private outside your project, for example `C:\Users\YOUR_WINDOWS_USER\superhuman-private\google-client.json`. Replace YOUR_GMAIL_ADDRESS below. Run the helper on Windows so the local callback reaches the browser on that laptop:

```powershell
python "C:\superhuman-os-starter\superhuman-v1.27-upgrade\gmail_connect.py" --client "$env:USERPROFILE\superhuman-private\google-client.json" --email "YOUR_GMAIL_ADDRESS" --slot personal_gmail --output "$env:USERPROFILE\superhuman-private\gmail-personal-transfer.json"
scp -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\superhuman_replacement" "$env:USERPROFILE\superhuman-private\gmail-personal-transfer.json" superhuman@167.71.196.20:/home/superhuman/gmail-personal-transfer.json
```

On Ubuntu, replace YOUR_GMAIL_ADDRESS and choose an existing workstream for the original email connector. This original workstream does not authorize sharing the private assistant's previews with a specialist.

```bash
chmod 600 /home/superhuman/gmail-personal-transfer.json
cd /home/superhuman/app
runuser -u superhuman -- .venv/bin/python -m superhuman.mail.cli import-gmail personal_gmail --email YOUR_GMAIL_ADDRESS --scope marketing --file /home/superhuman/gmail-personal-transfer.json
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli link-email personal_gmail
```

Import removes the server transfer file only after successful encrypted storage. Remove the Windows transfer copy afterwards. Keep the Google client file private. Repeat with the matching slot/address for other supported Gmail inboxes. Use Inbox to start remote reading, then enable the assistant controls. Attachments are excluded; the existing resumable email reader retains its own coverage/backpressure rules.

For Titan, use the original setup CLI with a mailbox/app password and the correct existing host profile, then link edsync_titan:

```bash
runuser -u superhuman -- .venv/bin/python -m superhuman.mail.cli connect-titan edsync_titan --email YOUR_TITAN_ADDRESS --scope edsync_product --host-profile titan
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli link-email edsync_titan
```

The hostname profile must match your actual provider. Supported existing profiles are godaddy, titan and titan_eu. This release does not introduce Outlook/Microsoft mail support.

## Slack

Create an internal Slack app in the intended workspace and obtain a token whose account may read the conversations you choose. Ask your workspace administrator if app installation or scopes require approval. Use only the history scopes needed for your selected public channels, private channels or DMs: channels:history, groups:history, im:history and/or mpim:history. Public/private channel thread reads through conversations.replies generally need a user token with the appropriate history scope; bot tokens have narrower thread access. Do not request chat:write for this integration.

Get the exact workspace ID and exact conversation IDs from Slack. A DM uses its D conversation ID, not the U ID of a person. The connector does not discover or enumerate all your channels, resolve people by name, invite a bot or read another user's inaccessible DMs. Grant only conversations the token is legitimately permitted to read.

Replace the example IDs/labels, then enter the token at the hidden prompt:

```bash
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli connect-slack --team-id T12345678 --label "Mahnoor Slack"
```

The command calls auth.test and refuses a mismatching workspace before saving. It prints a local channel_id. Use that exact ID in the next command, or add the conversation through the connection page:

```bash
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli allow-slack LOCAL_CHANNEL_ID --conversation-id C12345678 --label "Selected project channel"
```

Enable reading in the app; inspect a real preview; enable model processing separately. One workspace connection supports up to ten selected conversations. Reads are limited to 15 messages per page and at least 61 seconds between workspace HTTP calls, with Retry-After handling. The first scan is bounded to seven days. Page boundaries and cursors survive restarts. Discovered recent threads are followed separately, up to 100 active threads; a channel's history is not complete thread history. No files/media are fetched. Edits are detected only when a preview is refetched, not by a complete Slack event subscription. Replies in older or undiscovered threads can be absent.

If Slack reports invalid_cursor or missing_scope, inspect the account/scopes and coverage error. After fixing the cause, list the selected conversation records with this read-only command to get the stream ID and version, then authorize a bounded rescan:

```bash
runuser -u superhuman -- .venv/bin/python -c 'import json; from superhuman.comms import store; print(json.dumps({a["label"]: store.streams(a["id"]) for a in store.channels() if a["kind"] == "slack"}, indent=2))'
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli rescan-slack STREAM_ID --version STREAM_VERSION --note "Inspected token and pagination; rescan this selected conversation"
```

A rescan repeats the bounded read and deduplicates by source identity; it does not reset costs or erase saved artifacts. Disconnect/reconnect rotates credentials but keeps saved source identity and requires renewed consent.

## WhatsApp Business

Use a Meta developer app and a registered WhatsApp Business Platform/Cloud API business number you control. This is not a WhatsApp Web session, personal-account scraper or history export. Personal WhatsApp conversations and old chat history are unavailable through this adapter. Meta setup/approval, number registration and permission requirements still apply.

Obtain the **business phone-number ID** and the Meta app secret. Create a separate private verification token of at least 20 characters. In the server terminal:

```bash
runuser -u superhuman -- .venv/bin/python -m superhuman.comms.cli connect-whatsapp --phone-id YOUR_BUSINESS_PHONE_NUMBER_ID --label "EdSync WhatsApp Business"
```

Enter the Meta app secret and your verification token at the hidden prompts. This adapter does not need an outbound access token or implement message sending. Its connection identity remains pending until a signature-valid webhook for that phone-number ID arrives.

In the app, enable reading for this connection. Configure the Meta webhook callback URL as:

`https://superhuman.167-71-196-20.sslip.io/hooks/whatsapp`

Use the same verification token for Meta's challenge. Subscribe the app to the appropriate WhatsApp Business account's messages events, following Meta's account setup. A successful URL challenge is not proof that the business account is subscribed or that messages are flowing. Meta must accept the publicly reachable HTTPS host/certificate; if it refuses this hostname, use your own configured domain and update the app's origin through the existing hosting setup.

Send a real test text from another permitted phone to the registered business number. Check the matching source preview. The endpoint verifies each POST's HMAC-SHA256 signature against the app secret before accepting JSON and checks the configured phone-number ID. Replayed provider message IDs are deduplicated. Only the exact webhook path is public; the rest of the app remains signed in and protected by CSRF. There is no attachment download or outbound reply.

Enable Twin model processing only after reviewing the received preview. Disabling reading or disconnecting rejects future webhook receipt for that connection; revoke the subscription separately in Meta if desired. Offline servers cannot receive messages until Meta retries, and this release makes no guarantee about Meta's retry/history coverage.
