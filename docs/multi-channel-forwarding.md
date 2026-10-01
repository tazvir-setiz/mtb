# Multi-channel forwarding audit

## User flows

- Channel management lists every source/destination, ten at a time. Add preserves existing channels; removal uses the exact role and Telegram ID. The same Telegram channel can have both roles. Listener refresh removes the previous handler; queued events from that handler are ignored.
- Manual transfer selects one historical source and a destination subset before accepting a range or explicit message IDs. A message ID is never interpreted across multiple sources. Confirmation revalidates the stored selection against current configuration.
- Auto-forward subscribes to all configured sources and sends to all configured destinations. Both auto and manual forwarding use `fanout.fan_out`: one Guard preparation followed by independent destination deliveries.
- Progress and final counts describe destination deliveries. Recent history and errors include route IDs. Dashboard and statistics show multiple channels explicitly.

## Persistence and compatibility

- Each destination retains its own ordinary `ForwardJob` and `JobMessageResult` ledger. `job_routes:<primary_job_id>` stores the ordered list of participating jobs, and `job_selection:<job_id>` preserves sparse selections. Missing group metadata means the old job's one route. Pause/resume uses the least advanced route cursor; successful deliveries remain protected during replay.
- Retry reads job ledgers as well as legacy forwarding records, because another operation can take ownership of the canonical route record. It sends only failed/missing routes, never successful or skipped routes.
- `review_routes:<review_id>` retains the existing JSON list of `{destination_id, job_id}` objects. Additional destinations merge into one review for a source message. Invalid, empty, or missing metadata falls back to the old `ReviewRequest.destination_id/job_id` fields. Approving an old jobless review creates a delivery job so future flows can see its success.
- Full history clearing removes reviews, drafts, route metadata, job selections, jobs, result ledgers, and send markers together. Ordinary configuration remains intact.
- SQLite startup only replaces the old unique Telegram-ID index with uniqueness on `(type, telegram_id)` plus a lookup index. It does not rebuild tables, reset data, or change existing row IDs. The migration is idempotent.

## Concurrency and uncertain delivery

All application send flows acquire a source-message lock before review lookup/preparation, then the same canonical route lock for delivery. Route identity is `(source_channel_id, source_message_id, destination_channel_id)`. The success check is repeated inside the route lock, and successful results are immutable.

A `route_sending:<source>:<message>:<destination>` marker is committed before sending. Success is recorded before removing the marker. Definite Telegram rejections remove it; unknown/network outcomes and process interruption leave it in place. Subsequent attempts require review. Admin reset is the explicit authorization to retry an uncertain outcome; other successful destinations are still excluded. These locks coordinate the application's single event loop, as in the existing deployment; this is not a distributed worker queue.

Review approval uses the same delivery primitive, prepares with `approved=True`, and does not rerun Guard. Only the explicit AI rewrite action invokes the rewriting pipeline. Known destination failures leave the shared review pending for the missing routes.

## Single-channel search classification

| Occurrences | Classification |
| --- | --- |
| `ChannelRepository.get_by_type` definition and repository tests | Legacy low-level compatibility API; no application screen or transfer uses it to choose a route. |
| `get_channels(selection)` in transfer handlers/input | Explicit selected source and selected destination list; singleton defaults preserve the old configuration. No argumentless application calls remain. |
| `ForwardJob.source_channel_id/destination_channel_id`, repository models, result storage | Valid per-route fields retained for SQLite compatibility. |
| `job.source_channel_id/destination_channel_id` in resume/retry | Legacy call signature; the runner resolves the entire persisted job group before sending. |
| `ChannelType.SOURCE/DESTINATION` in management/dashboard/statistics/listener | All-channel queries or exact role operations. |
| `send_prepared_message` in fan-out/review | Called through the common locked delivery primitive. |
| `prepare_message` in auto/manual | Passed once to common fan-out, before its destination loop. |
| `prepare_message` in review approval | Once with `approved=True`; no Guard rerun. |
| `message_sender.send_message`, `_send_message`, `fetch_and_send_message` | Retained low-level compatibility helpers tested independently; production auto/manual/review flows use preparation plus common delivery. |
| `review_store.enqueue` | Compatibility wrapper for one route; application fan-out uses `enqueue_routes`. |
| Bot `send_message` in review notifications | Administrative notifications, not channel forwarding. |

## Validation scope

`tests/test_multi_channel.py` covers the 1→1, 1→N, N→1, N→N matrix, Guard spies, shared review/approval/rejection, partial failures, route reassignment, missing/skipped/successful retries, uncertainty/restart markers, cross-flow races, selection, pagination, listener refresh, legacy review resolution, and SQLite index migration. Existing forwarding, UI, review, and repository regressions remain in place.

The starting branch's full suite could not collect eight Guard files because its tests referenced the removed composite Verification API. With explicit user authorization, tests were migrated to the existing separate classification/decomposition/rewrite/policy/meaning stages. Confirmed regressions in failure-circuit accounting, schema diagnostics, and raw-response logging were repaired; documented limits now match Guard defaults. No tests were deleted, skipped, or marked xfail.
