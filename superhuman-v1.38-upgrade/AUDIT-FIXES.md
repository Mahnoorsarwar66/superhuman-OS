# Live QA finding map

| Finding | Implementation | Verification |
| --- | --- | --- |
| SH-15 Project Conversations omits channels/topics | One renderer lists exact-project channels, milestone topics and project rooms. Compatibility route delegates to it. Internal contribution rooms are excluded. | Authenticated HTTP tests for both entry points, archive discovery, foreign-project exclusion and escaped titles. |
| SH-16 Disabled Team accepts a queued discussion | Shared readiness checks render the blocker and guard send/retry in the enqueue transaction. Existing queued history is labelled as waiting and remains cancellable. | Disabled/held Team, paused worker/project/recipient, expired budget, missing rates, revoked sharing, idempotent replay, atomic in-transaction hold, blocked retry and no-write/no-cost checks. |
| SH-17 Duplicate Complete option | One filter combines governed `complete` and earlier `approved` records; old bookmarks normalize to it. | HTTP test contains both project types and exactly one Complete option. |
| SH-05 Remaining availability copy | Shared execution-control wording in baseline/employee administration/Twin profile; heartbeat uses Connected rather than Available. | HTTP checks across the affected surfaces. |
| Partial SH-01 and SH-08 | Existing metering and task-conversion protection retained; no unsupported migration or spending bypass added. | Existing budget negative-path/concurrency/accounting regressions plus retained-task conversion/link checks. |

The installation does not claim that the uncompleted live multi-agent production test has passed. There is no new project-only execution switch. Research quality, full guide comprehension, independent judgment and business impact still need the controlled acceptance run.
