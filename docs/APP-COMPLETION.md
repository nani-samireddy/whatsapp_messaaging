# WhatsApp app completion status

Updated 30 October 2026. Work is limited to the Mac development checkout and isolated local tests. Existing tutorial files are preserved.

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

On 30 October, **30 dedicated document-delivery integration checks passed** on the disposable local document-test site. These cover Data comparisons, multiline Text equality/Contains, transition deduplication, unchanged source records/metadata, permission-filtered Data suggestions, private PDFs, staff release and canonical outbox behavior. Provider transport was mocked. Native browser checks verified chips, slash search, custom values, removal and saving. No patient message or Meta template submission was made by these checks.

The 23 October fresh-install run passed **176 integration checks**, and **26 local regression checks** passed. The app assets rebuilt successfully. The integration tests use transport mocks on an internal-only network and do not contact Meta or existing sites.

The 23 October pass corrected missing contextual help on Media/shared-field policies and outdated documentation about field-policy authority, campaign editing, Meta authoring and media ID reuse. See [automatic document delivery](DOCUMENT-DELIVERY.md) for the subsequent local setup and its inactive presets.

Evidence: [completion validation](validation/app-completion-2026-10-23.json). Prior UI/workflow checks remain in the individual feature validation files.

## Remaining acceptance work

1. Validate the configured Meta account with an opted-in test recipient: text/template send, private media upload and recipient delivery. Local mock results do not establish these provider capabilities.
2. Validate Meta review outcomes and signed inbound/delivery callbacks through a reachable HTTPS callback in an explicitly selected test environment. The current work has not provisioned public ingress or changed the home server.
3. Verify scheduler/worker and reconnect behavior in that live test environment, then complete user acceptance of the hospital's actual source-record mappings and permissions.

These are outstanding checks. This document does not declare the app production-ready.

## Current feature boundaries

The local Meta authoring editor supports Utility/Marketing text templates, positional body variables and fixed text headers/footers. Approved DOCUMENT-header templates created in WhatsApp Manager can be synchronized/imported and used for per-record PDFs through document-delivery rules. Their header is not authored through the local text editor. Other media headers, header variables, buttons, authentication templates and named parameters remain unsupported. Local messages support private JPEG/PNG images and PDFs. Audio, video and stickers remain outside the implemented media workflow.

The original baseline review remains historical evidence; use this document and current workflow documentation for the implemented scope.
