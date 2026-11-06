# WhatsApp app completion status

Updated 1 November 2026. Work is limited to the Mac development checkout and isolated local tests. Existing tutorial files are preserved.

## Implemented scope

| Workflow | Current behavior |
|---|---|
| Access and navigation | Existing login/roles, three workspaces, permission-aware summaries and readable record titles. |
| Sender and settings | Encrypted long access tokens, field help/documentation references, WABA identity and separate outbound/inbound/automation controls. |
| Content | Shared source/settings field picker, automatic text/image/document detection, caption switching, live preview, fixed text header/footer. |
| Meta templates | Selective import modal, explicit variable mappings and review examples, deliberate submission, status refresh and rejection guidance. |
| Media | Private file validation and preview in Quick Entry/full form, selected sender, after-commit cloud upload, upload status/retry and bounded ID reuse. |
| Campaigns | Shared content reference, audience/phone mapping, filters, bulk preview/start, document events, schedules and durable run tracking. |
| Automatic documents | Generic rules for generated private PDFs or a source record's private PDF attachment; approved DOCUMENT-header templates, recipient mapping, optional staff release and delivery history. Select/Data fields share chips with slash suggestions; Text fields support Equals/Contains. |
| Inbox | Text/template/private attachment composition, assignment, read state, business-record context and idempotent queue requests. |
| Delivery and inbound | Durable outbox/attempts, signed batched webhooks, duplicate handling, non-regressing delivery receipts, quarantine/replay and uncertain-outcome handling. |
| Help | 22 searchable workflow pages with screenshots and Markdown copies, including automatic documents and reviewed laboratory reports. Document rule and delivery forms include Help → User guide. |

## Latest local verification

The 1 November production review closed attachment access, stale worker claim, delivery-receipt and source/recipient revalidation gaps. WhatsApp Settings now includes a System Manager-only **Check setup** action (under Menu on narrow layouts); it sends nothing and changes no configuration.

- Fresh installation: **268 passed, 1 HMS-only case skipped**.
- Legacy upgrade from `d55395f`: **266 passed, 1 HMS-only case skipped**, including plaintext-to-encrypted credential migration with outbound requests still off.
- Final regression including media redirects and legacy shared-upload compatibility: **268 passed, 1 skipped**.
- Separate HMS document-delivery suite: **30 passed**, including the invoice case skipped by the app-only harness.
- Local regressions: **77 Python and 18 JavaScript checks passed**. Syntax/whitespace checks passed.

Provider transport was mocked. Fresh-install/upgrade networks had no external route. The real PDF renderer fetched only built public assets from container loopback. Tests used isolated fixtures and did not send patient messages or submit Meta templates. The operational sites' sending switches were not changed.

Evidence: [production review validation](validation/production-readiness-2026-11-01.json), [production setup and acceptance](PRODUCTION-READINESS.md), and [all 36 DocTypes / naming recommendations](DOCTYPE-NAMING-REVIEW.md).

## Remaining production acceptance

1. Configure and verify the selected deployment's public HTTPS URL, Meta account/sender credentials and permanent signed webhook callback. Repeat opted-in template/reply/image/PDF delivery on that deployment; prior Mac-local live tests do not certify a different installation.
2. Run supervised default and `whatsapp_media` workers and the site's scheduler. Verify actual recurring 09:00 reminders, restart/reconnect behavior, hospital source mappings, consent and user permissions. The Mac-local read-only check currently reports its development URL, no recent scheduler evidence and missing default/media-worker heartbeats.
3. Verify Meta review/rejection outcomes, inbound attachment handling, larger controlled batches and a successful backup restore rehearsal on the deployment.

Eight business/child DocTypes now have clearer names, including Additional Numbers, WhatsApp Sender and WhatsApp Contact. Record IDs remain unchanged. See DOCTYPE-NAMING-REVIEW.md for the mapping and REST resource-name changes. The review does not declare the app production-ready until these deployment checks pass. Prior implementation evidence remains in the dated validation files.

## Current feature boundaries

The local Meta authoring editor supports Utility/Marketing text templates, positional body variables and fixed text headers/footers. Approved DOCUMENT-header templates created in WhatsApp Manager can be synchronized/imported and used for per-record PDFs through document-delivery rules. Their header is not authored through the local text editor. Other media headers, header variables, buttons, authentication templates and named parameters remain unsupported. Local messages support private JPEG/PNG images and PDFs. Audio, video and stickers remain outside the implemented media workflow.

The original baseline review remains historical evidence; use this document and current workflow documentation for the implemented scope.

## Plain-language update — 1 November

Reviewed all 36 DocTypes. Renamed eight confusing business/child types and simplified field labels, menus, action buttons, event choices, status summaries and help. Raw diagnostic data is collapsed under Technical Details. Form introductions describe each record’s purpose. Updated the 22 workflow guides and captured the new Additional Numbers form. The three workspaces retain their layouts.

Final tests: **271 passed / 2 skipped** on a fresh installation, **272 passed / 1 skipped** upgrading from `04ad660`, plus **77 Python** and **18 JavaScript** tests. Skips are the upgrade-only fixture on fresh install and the HMS-only invoice case in the app-only harness. Migration fixtures cover encrypted tokens, saved numbers and selections, private files, permissions, record links, shared field approvals, query filters and uncertain sending requests. The actual local-site records, encrypted credential values, sending switches and message counts matched their pre-migration snapshots. No server deployment or provider send was performed.

Runtime follow-up: corrected stale Mac-local web/worker/helper processes after the DocType rename. Verified the authenticated WhatsApp Messaging workspace renders its summary after restarting them; all three summary services also pass in a fresh process. Cache clearing alone does not reload Python modules in a `--noreload` web server. The server deployment was not changed.

## Inbox and conversation form — 1 November

The Inbox now uses two main columns, All / Unread / Mine quick views, collapsed secondary filters and an optional Contact details panel. Escape closes that panel and returns focus. Message reply actions appear on hover or keyboard focus, and on touch devices. Shorter timestamps and a smaller composer reduce clutter. Direct replies, emoji and ordinary attachments are unavailable outside the permitted reply window; the template action remains available subject to the existing permissions and consent checks. Drafts are locked while a send is in progress.

Live conversation forms now show read-only, paginated message history using the Inbox’s existing authorized reader. Load older messages exposes the entire history; private attachment links use the existing download authorization. Viewing the form does not mark Inbox messages read. Open in Inbox opens the same conversation for replying. The local example was verified with all 41 messages and 3 attachment links.

Repaired the Administration shortcut that still named WhatsApp Template Field Policy. A follow-up patch repairs stored targets and labels without recreating workspace rows or replacing layouts. Source-navigation and real-schema regression checks cover every shipped workspace/sidebar target and a deliberately stale shortcut.

Verification: **273 integration cases passed, 2 skipped**, **78 Python tests**, **25 JavaScript tests**, successful asset build, and desktop/mobile browser checks. The integration skips are the upgrade-only fixture and HMS-only invoice in the app-only harness. No new sending requests were created; production was not changed.
