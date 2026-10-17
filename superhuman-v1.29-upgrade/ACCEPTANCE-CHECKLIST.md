# v1.29 live acceptance

1. Sign out and sign back in using the browser. The login page must not produce an immediate “form expired” error from background app assets.
2. Create a managed project from Projects. Confirm that its department summary and project list show it. Add one task; the department task count should increase by one. Starting that task must not add a second business project/task count for its execution.
3. Open Overview, Reviews and Attention. Their decision queue should agree, and each item should open the appropriate task, proposal or meeting.
4. Open Team → Mahnoor Twin. Chat, Owner updates and Communications should sit together. Old Twin and Personal assistant landing links should lead into these tabs.
5. Start a global Twin chat and ask about an existing saved briefing. It should distinguish saved information from live message access. Check that a project-specific Twin chat does not inherit unrelated global inbox context.
6. Select Jose in Conversations. Sarah's rooms should not appear in Jose's filtered list. Search titles, go to an older history page and open older messages in a long chat.
7. Send a chat message; wait without reloading. When the worker saves a reply, it should appear. Start composing another message while a reply completes; your text must remain. Reload with an unsent draft and check it returns.
8. Cancel a queued reply, request a fresh reply after reviewing a failure, and update a reached reply allowance. A running/billed request must not be presented as safely cancellable.
9. Review a conversation proposal. Check project minimums, risk, sensitivity and acceptance criteria. Public/Internal instructions require explicit sharing confirmation. If you authorise the exact task's start here, a second start grant should not be necessary; budget/tool/employee/project checks still apply.
10. Correct a conversation's project location only if all of its history belongs there. A pending reply or proposed task should block the move. History should remain intact afterward.
11. On the employee board, let an assignment change. Confirm the visible task, Open task link, project link and last-action label update together. Offline/paused status must reflect the worker controls.
12. Use All tasks filters for department, employee, priority, status and overdue dates. Open the task and verify readable instructions/output and appropriate controls.
13. Filter Inbox by account and search term. Select a message, save its review state or edit a local draft, and verify your position is retained. Nothing should be sent externally. Reading and model consent remain separate.
14. Switch Calendar Month/Week/Day/Agenda. Confirm the selected mode is highlighted and today's date remains readable. Search meetings, pick a date, create a local meeting and reschedule it in PKT. Check planning deadlines beside the chosen dates/range.
15. Preview an invitation such as `Meeting 2026-10-16 09:00 America/New_York`: it should show 18:00 PKT before confirmation. Missing/ambiguous zones and repeated daylight-saving hours still require clarification. Check possible overlaps before saving; unknown durations and unimported meetings cannot be fully checked.
16. Check English/Urdu Dictate on your actual device. Edit the transcript and press Send manually. Typing must remain available when recognition is unsupported or permission is denied.
17. Confirm `/healthz` reports 1.29.0, both services are active and System checks has no new unexplained failures.

Navigation checks do not require model calls. Sending chats, briefing requests or analysis uses your existing budget. Record any remaining issue by screen, action, expected result and actual result; omit private message content and credentials.
