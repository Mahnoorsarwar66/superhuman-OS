# Local validation record — v1.27

Prepared 2026-10-16 against the delivered v1.26 source. The final staged installer passed **664 automated tests: 614 inherited and 50 new communications tests**, then installed into a disposable v1.26 fixture. The code ran under local Python 3.12 using synthetic accounts, fake provider responses, fake model usage/rates and isolated data. No real account or paid model was contacted by the tests.

New coverage includes explicit read/model consent, encrypted credential handling, missing-key protection across both legacy email and communications setup, expected Slack identity, selected conversations, pinned pagination, terminal-page watermarks, throttling, Retry-After, recent thread reads, in-flight revocation, exact source deduplication, source edits, possible-duplicate provenance, email generation checks and honest sync timestamps.

WhatsApp cases cover challenge verification, HMAC validation, incorrect signatures, matching business-number IDs, replay deduplication, disconnect, exact public-route isolation, private-page authentication/CSRF, HTML escaping and request size limits. Model/workflow cases cover valid source references, strict JSON, secret masking, malformed replies, local drafts, owner-only private task sharing, source staleness, public-web exclusion and owner repair of legacy private runs, daily ceilings, reserved scheduled attempts, idempotent slots, stale-brief supersession, owner retries, restart holds and the existing worker loop.

Separate lifecycle checks passed:

- Already-installed checksum/integration verification makes no changes.
- Tampered installed source is refused before rollback.
- All ten replaced source files restore byte-for-byte to v1.26.
- Private sources, encrypted connector records, Team tasks, artifact sentinel, audit rows and dollar budget survive rollback.
- Communications controls, pending jobs and Team are disabled; the worker stays paused.
- Reapplied source is recognized and recovery retains data with explicit reauthorization required.
- An unrecognized v1.26 baseline is refused before creating an installation or backup.

Python compilation and Bash syntax checks passed. ZIP CRC and SHA-256 file-list integrity checks passed. Credential files, databases, encryption keys, source backups, runtime manifests, agent-registry fixtures and Python caches are excluded from the release.

The staged test environment has the existing application dependencies. The release adds no server Python dependency. Existing runner/export boundaries are covered by inherited tests; no live Docker workload or browser visual audit was performed.

Not validated here: the production Ubuntu host/systemd/Nginx, live Gmail/Slack/Meta permissions, external account approval, real webhook delivery, real model quality, production traffic volume, provider invoices or an end-to-end live audit. Follow the connection guide's first-source and next-slot checks after installation. Accounts start unconfigured and no remote connection is implied by delivery of this ZIP.

## v1.26 packaging correction

The previous v1.26 ZIP omitted the Gmail setup helper referenced by its inherited tests. It has been restored in the corrected download and its five helper tests pass. The v1.27 ZIP includes the helper too. A v1.26 installation that failed that staged check did not switch source; install the corrected prerequisite before v1.27. v1.26's functional source is unchanged by this packaging correction.
