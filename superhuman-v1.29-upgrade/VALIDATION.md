# v1.29 validation — 16 October 2026

## Automated checks

- **738 Python tests passed**, including **38 new cross-screen workflow tests**, in the final installer's isolated staging workspace. Final run: 204.491 seconds in the build environment. The staged app used the preserved production CLI and metered orchestrator variant supplied during this project.
- New tests cover department/Team project and task agreement, execution deduplication, scoped counts, readable next-step destinations, employee chat filtering, full history paging, room moves and version conflicts, explicit approval classifications, project minimums, private-sharing confirmation, approval idempotence, consent-aware saved briefing context, revocation during a reply, Reviews/Attention consistency, Inbox position and email-source conversion, PKT rescheduling, private live endpoints and login asset isolation.
- Browser dictation contract checks passed for the three conversation composer types. JavaScript and Bash syntax checks passed. Existing provider/model calls were mocked; no paid model requests or real external messages were made.

## Real browser checks with synthetic local data

A disposable local HTTPS app was exercised with headless Chromium and Playwright at desktop 1440×1000 and mobile 390×844 sizes. The browser and its dependencies are not included in the upgrade.

- Sign-in succeeded through the actual browser form after the protected-login-assets bug was fixed.
- Overview, Projects, department summary, employee board, Inbox, Calendar and Twin pages opened without browser JavaScript errors.
- Desktop and mobile page-width checks found no unintended document-level horizontal overflow in the exercised views. Calendar grids retain their own bounded scrolling where appropriate.
- A saved chat reply appeared through live refresh without a page reload. An unsent draft survived the update and a manual reload, and cleared after successful sending.
- An employee's assignment changed; the board title and Open task link updated to the new task together.
- Calendar view highlighting and desktop/mobile layouts were inspected. Today's date remains visible in its highlighted circle. Screenshots were used for internal QA and are not included in this installation.

These are representative browser checks, not a guarantee for every device or browser. Real microphone recognition and actual live provider connections still need the acceptance checklist.

## Installer and rollback

- Exact v1.28 integration installed successfully in a disposable app copy.
- A repeated preflight recognised the installed v1.29 release and made no changes.
- An unrecognised v1.28 source was rejected without source or data writes.
- The production CLI and budget-metered orchestrator stayed byte-for-byte unchanged.
- Rollback refused an unexpected owner-added file before mutation. After removing that test file, rollback restored every original integration hash and retained project records, room associations and message history. A pending room reply was cancelled and the worker was left paused for inspection.
- Python integration and authenticated CSS/JavaScript assets are covered by installer hashes. ZIP integrity and the packaged file list were checked before delivery.

The user's live server has not been upgraded or audited by these local checks. Run the included server launcher and live acceptance checklist to verify the actual deployment.
