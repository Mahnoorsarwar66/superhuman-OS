# Validation — 16 October 2026

- 700 Python regression tests passed in the installer's isolated staged workspace, including 36 new experience tests. The final run used the production CLI and budget-metered orchestrator variant corresponding to the files supplied in this conversation. No paid model requests or live provider calls were made.
- Installation from the exact v1.27 integration completed in a disposable fixture. The manifest records v1.28.0 and hashes both authenticated CSS/JavaScript assets.
- A repeated preflight recognised the installed release and made no changes.
- An unrecognised integration source was rejected before source/data writes.
- The production CLI and metered orchestrator remained byte-for-byte unchanged.
- Rollback rejected an unexpected owner-added package file, then succeeded after the extra file was removed. Every original integration hash was restored. Owner project records, room associations and message history were retained; pending Team Room replies were cancelled and the worker was left paused.
- Browser-API contract tests passed for the existing Talk composer, Twin owner updates and new Team Room composer: English/Urdu selection, editable transcript, text limits, one active recorder, stopping on submit and unsupported-browser fallback. Dictation never auto-submits.
- Bash syntax checks, Python parsing, JavaScript syntax and ZIP integrity checks passed.

Live deployment, real microphone recognition, rendered browser layout and actual provider sync still require the included acceptance checklist. A headless browser could not be installed in this build environment, so browser rendering was not visually verified. This release makes no claim that the live server has been audited or upgraded.
