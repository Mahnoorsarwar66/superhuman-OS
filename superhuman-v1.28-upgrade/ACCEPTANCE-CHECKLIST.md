# v1.28 live acceptance check

No external actions or new paid analysis are required for navigation checks. Sending an AI chat message does use your configured model budget.

- Overview → Work briefing: Overview remains highlighted; the briefing opens in the main workspace.
- Departments → any department: the original six tabs plus Agent and Supervision appear. No duplicate global department/priorities/supervision strip.
- Agent names match the seven requested mappings. Existing writing skills and permissions remain intact.
- Projects → All tasks and Suggested work: real saved items link to their source/project. Coding remains in the sidebar. Legacy processing records remain available through diagnostics.
- Create two project rooms for different projects in the same department. Each project's Conversations lists only its own room. Old department conversations are not automatically assigned.
- Team → Team Room: start a Twin chat and a specialist chat. Confirm that a message queues one reply and creates no immediate task/external action. Pausing an employee prevents new chat replies until resumed.
- Team → Team activity: existing handoffs/challenges/questions and saved responses open their original review controls. No activity is invented for an idle team.
- Team → Employee board: idle, queued, reviewing and offline states agree with the actual task and worker records. Do not interpret all cards as simultaneously running.
- Talk, Team Room and Twin owner updates: Dictate appears. Test English and Urdu, stop dictation, edit the transcript, then manually Send. Test denied permission or an unsupported browser and confirm typing remains possible.
- Inbox: compare connection labels and actual last check against the existing provider settings. Search/select a message, change its local review state, open its original workspace and review its local draft. Check that opening the page does not enable reading/AI or send anything.
- Calendar: switch Month / Week / Day / Agenda. Open an existing event and a meeting workspace. Check planning deadlines and the existing calendar download links.
- Invitation intake: paste `Meeting 2026-10-16 09:00 America/New_York`. Preview must show 18:00 PKT on that date. Confirm only if you want this synthetic test meeting saved, then cancel/delete through existing event controls as applicable.
- Cross-midnight example: `Meeting 2026-10-16 23:30 America/Los_Angeles` must show 11:30 PKT on 17 October.
- Ambiguity: `Meeting 2026-11-01 01:30 America/New_York` must require the first/second occurrence. A missing timezone or `IST` must require clarification.
- Check `/healthz` reports 1.28.0 and both services are active. Check the existing System checks page; do not infer successful provider sync from a green navigation screen.

Record remaining issues by screen, exact action and visible result. Share screenshots only after removing private message content and credentials.
