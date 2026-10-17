# v1.30 validation

- 783 offline tests passed in the real installer's staged source tree (738 retained tests, updated for intended release/name/navigation changes, plus 45 new foundation tests). Runtime: approximately 213 seconds in the build environment.
- The isolated installation completed against v1.29 source while retaining a production CLI/orchestrator variant. Both protected files remained byte-identical.
- Idempotent installed-source verification passed without writes.
- Rollback refused an extra owner-added package file before changing source. After its removal, rollback restored every original integration hash.
- Rollback retained projects, Storage records, uploaded source bytes, personality edits and saved baselines; the worker and scanner were paused. Rolled-back source passed the reinstall preflight.
- Authenticated browser checks exercised desktop and mobile Storage, retrieval preview, persistent personality edits, alert acknowledgement and saved baselines. No body overflow or page JavaScript errors was observed on the checked views. Screenshots are internal validation only and are not included.
- New tests exercise named sharing, sensitivity ceilings, project boundaries, draft/archived exclusion, conflicting facts, due reviews, file hash changes, missing files, metadata version conflicts, mid-reply revocation/personality changes, guarded file tools, saved-source receipts, rule throttling, acknowledgement/resolution/reopening, opt-in Twin review and local baseline privacy.
- Python syntax checks and shell syntax checks passed. The archive contains source, references, tests and instructions; no browser runtime, credentials, owner data or replacement agent registry.

## Limits of this evidence

The server has not been accessed for this build. Tests use synthetic local records and mocked model/provider responses. They do not establish live model access, current email/Slack/WhatsApp connectivity, external-action support or real departmental outcomes. The baseline page explicitly distinguishes saved historical evidence from configuration and current live proof.
