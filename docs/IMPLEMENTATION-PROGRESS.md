# Implementation progress

The canonical checkout is `/Users/samireddynani/projects/frappe/development/frappe-bench/apps/whatsapp_messaging`. Implementation work was collected on `feature/whatsapp-messaging` for integration into local `develop`. Remote publishing and server deployment are separate from this local merge. The home server was not accessed or changed. The earlier standalone checkout is retained as a recovery copy.

## Implemented

- Reused Whatsapp Editor and Whatsapp Admin with existing Frappe sessions. Single sends/history are available to both; campaigns require Admin/System Manager. Both app roles can activate event automations and schedules. Credential administration remains System Manager-only. User role assignments were not changed on either Mac site.
- Retained the security foundation: encrypted/masked tokens, permission level 1 configuration and approved source mappings, safe template rendering, source/account/template checks, strict Graph URL construction, bounded network requests and default-off dispatch.
- Added three standard workspaces and a module sidebar: Messaging, Templates & Automation, Administration. Their summaries use current-user permissions and truthful empty states. The app is registered in Desk's app chooser alongside HMS, with the existing app roles controlling visibility.
- Implemented canonical conversation/message history, peers/identity aliases, personal read cursors, workflow assignment/status, explicit business record links/activity, and private image/PDF attachments.
- Added an in-app searchable user guide with 19 hospital workflow pages, screenshots, role labels, related links, workspace/sidebar shortcuts and contextual Help links. Media and shared-field policies include contextual help. Markdown copies are available in [the user guide](user-guide/README.md).
- Added a responsive inbox with text/template/attachment composition, idempotent requests, safe rendering, drafts during navigation, personal unread state, post-commit user-room hints and polling recovery.
- Replaced direct legacy transport with durable outbox/attempt records, after-commit jobs, lease recovery, pacing, explicit retries/cancellation, provider-acceptance versus delivery states and Unknown handling.
- Added signed durable inbound/status webhook processing, duplicate-safe batched ingestion, non-regressing delivery projections, unknown-account quarantine and replay. No callback infrastructure was provisioned.
- Added the WABA-scoped Meta catalogue, selective import, explicit content submission/status checks and rejection guidance. Content supports positional body variables and fixed text headers/footers. Templates own content; Campaigns own audiences and sending rules. System Manager controls shared source/settings field policies.
- Rebuilt schedules and campaigns around fixed jobs and durable runs, executing as the activating user. Includes one-hour schedule catch-up, skipped older occurrences, paginated previews/expansion, one message per source record/recipient, pause/resume/cancel and separate expansion/delivery counts. Old encoded jobs are stopped.
- Preserved legacy rows without assuming sender identity, delivery or an inbound window. New writes use canonical records. No historical automatic resends or retention deletion.

Full behavior and operating notes: [workspaces and inbox](WORKSPACES-AND-INBOX.md). Current role matrix: [role permissions](ROLE-PERMISSIONS.md).

## Mac development rollout

During the original 18 October rollout, both `hms.localhost` and `development.localhost` were backed up (database, configuration and files) before migration. Assets and schema were applied locally with the integration switches initially off. Subsequent administrator configuration is separate from automated testing. Test/training fixtures have not been seeded into either site.

Isolated fixtures use a separate internal Docker network/database/Redis/bench volume. Tests mock all provider transport. Browser checks use fictional users in this disposable environment; no role assignment or test message was added to the Mac sites.

## Validation history and remaining external checks

- Latest completion pass, 23 October: **176 integration checks on a fresh install and 26 local checks pass**. Assets rebuilt and caches cleared on both development sites. See [completion status](APP-COMPLETION.md) and [validation](validation/app-completion-2026-10-23.json). Video production is stopped; existing files are preserved.

- Original foundation: [validation](validation/security-foundation-2026-10-18.json).
- Existing-role slice: [validation](validation/existing-role-access-2026-10-18.json).
- Workspace/inbox/automation implementation: **22 local tests and 88 Frappe integration tests pass**, including mocked provider transport and an RQ worker. Browser checks and both Mac site rollout checks pass. See [validation](validation/workspaces-inbox-automation-2026-10-18.json). The disposable test stack and proxy were removed.

Live Meta contract tests, public HTTPS webhook delivery, actual account/approval capabilities and production rollout remain outside this local implementation. The earlier [review](reviews/2026-10-18/REVIEW-AND-INBOX-DESIGN.md) records the baseline at `d55395fe92f576287c3a1a1778e135bf3e21f9d5`; its backlog and original membership/new-role suggestions are superseded where the implemented behavior and user decisions above differ.

User documentation validation: [hospital user guide](validation/user-guide-2026-10-18.json). The guide uses a single fictional Riverbend Hospital scenario throughout; demo records remain isolated from both Mac sites.
