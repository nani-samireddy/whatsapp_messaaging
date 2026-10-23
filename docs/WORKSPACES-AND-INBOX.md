# WhatsApp workspaces and messaging

Implemented in the Mac development bench app, with `develop` as the local integration branch. The two local sites are `http://hms.localhost:8000` and `http://development.localhost:8000`. They keep their existing Frappe users and login. Automated test and training fixtures use a separate disposable site; they are never seeded into these development sites.

## Workspaces

| Workspace | Access | Main destinations |
|---|---|---|
| WhatsApp Messaging | Whatsapp Editor, Whatsapp Admin, System Manager | Inbox, conversations, canonical messages, media, static recipients |
| WhatsApp Templates & Automation | All three roles | Reusable content, campaigns, schedules and runs; Meta sync/review and bulk preview/start require Admin/System Manager |
| WhatsApp Administration | Whatsapp Admin, System Manager | Sender accounts, integration settings, queue, webhook/status events, attempts, activity and legacy logs |

Each workspace has permission-aware summary cards that open the matching filtered destination. Zero-data sites show zero counts and setup guidance. The existing Messaging workspace and route are retained. All navigation belongs to the WhatsApp module, including its Frappe v16 Sidebar, without changes to HMS workspaces.

Inbox: `/app/whatsapp-inbox`. Automation: `/app/whatsapp-automations`. Frappe may redirect these aliases into its `/desk` routes.

## Everyday inbox workflow

Choose an account or all permitted accounts, filter by status, Mine, Unassigned or Unread, or search a recipient/name. Open a thread to read its timeline, claim/release it, change its status, link permitted business records, or compose a reply. Editors change assignment/status only on their own or unassigned conversations; supervisors can reassign eligible agents. Assignment is workflow and does not restrict the previously agreed shared read/send access.

The desktop keeps list, thread and details together. Phones use list-to-thread navigation with an explicit Details toggle. Drafts stay in memory per conversation while navigating and during refresh/reconnect; a browser reload ends the in-memory draft session. A stable request ID survives uncertain submissions, preventing double clicks/timeouts from creating duplicate intents. A periodic authorized refresh recovers missed realtime events; typing is not interrupted. Post-commit realtime hints use individual authenticated user rooms and respect conversation permissions.

Unread state is per user and monotonic. Incoming messages reopen resolved conversations. Local read state does not send a remote WhatsApp read receipt. Business record links require ordinary record-read permission both when linking and when opening; source-driven sends explicitly link their readable source. Matching phone numbers alone never links a business record.

Text replies, private JPEG/PNG images and PDFs are supported inside a reliable service window. The composer switches to supported approved templates outside that window. Initiating template messages require recorded consent; suppression blocks all sends. Admin/System Manager manages eligibility with an audit entry. New or changed eligibility is rechecked at dispatch. Unsupported incoming messages/attachments remain visible as placeholders or blocked assets.

## Message and queue integrity

WhatsApp Message is the canonical message record; Outbox stores one immutable logical intent and Send Attempt records its transport attempts. Both business-document buttons and all new inbox/automation entry points use these records. Legacy direct transport and encoded scheduler callbacks cannot send independently. Saving a Media record can queue a separate cloud upload; uploading does not create or send a message.

Queue publication occurs after database commit. Database sweepers recover missed jobs and expired leases. There is one in-flight dispatch lease per sender, with conservative account and peer pacing. Queued, Accepted, Held, Sent, Delivered, Read, Failed, Unknown and Cancelled are distinct outcomes. An accepted HTTP response does not imply delivery. Provider receipts are retained independently and read/delivered projections cannot regress with late receipts. Failed pre-acceptance requests may be deliberately retried. Unknown outcomes, accepted failures and uncertain transport are never blindly retried; a deliberate new message is a new intent.

Private attachment bytes are type/size checked and pinned by checksum when queued. Dispatch can reuse an unexpired cloud media ID for the same sender, checked content hash and readable library record. Otherwise it uploads the checked file before sending. Inbound download verifies the provider checksum and uses bounded HTTPS requests to known provider hosts and private File storage. Authorized downloads enforce conversation access. Bearer headers, secrets and raw provider error bodies are not placed in jobs, payloads or operator errors. See [Media library](MEDIA-LIBRARY-REVIEW.md) for the dedicated upload queue and lifecycle.

## Templates, schedules and campaigns

Message Templates own reusable content and Meta review; Campaigns reference them and own the audience and sending rules. Both remain editable by the existing app roles. System Manager approves shared source/settings fields once per DocType; template authors select from those approved, readable fields and enter fictional review examples. The Meta catalogue is synchronized within the sender's WABA. A supervisor can selectively import supported entries, explicitly submit saved drafts, and check review status. Syncing or saving alone does not submit content or send messages.

Meta authoring supports a text body, positional variables, fixed text header and footer, and Utility/Marketing categories. Local messages can use private images or PDFs with captions. Meta media headers, buttons, authentication templates and named parameters remain unsupported and are explained in the editor/import dialog. See [Templates and campaigns](TEMPLATES-AND-CAMPAIGNS.md) for review, rejection guidance and content-version handling.

Both app roles can activate document-event automations and schedules. Each rule/schedule records its activating user and rechecks their current role and business-record permissions when executing. Disabling a rule pauses its schedule. Scheduled/Cron templates use fixed dispatcher jobs and durable Schedule/Run records, not dynamically named Python methods. The schedule dialog also creates/updates these records directly.

Schedules use an explicit timezone and UTC occurrence keys. Missed occurrences within one hour can catch up once; older occurrences are reported as skipped. Invalid or ambiguous local DST times are rejected. Pausing prevents new dispatch claims; requests already in flight may finish. A disabled integration creates no dispatchable backlog from missed schedules.

Admin/System Manager can preview manual bulk templates and explicitly start a campaign. The preview freezes source identities/versions and rule version, displays exclusions and personalized content in pages, and never dispatches. Expansion creates **one message per business record and recipient**, deduplicating repeated numbers only within one record. Changed/unreadable sources are excluded, rather than silently sending changed content. A run supports pause/resume, cancellation of remaining undispatched messages, bounded expansion, counts and separate send outcomes. Completed means expansion completed, not successful delivery. Re-running an event retains its original source scope; re-running a manual send cannot turn into an Editor bulk query.

## Configuration and local operation

One Meta application is configured per Frappe site, with multiple sender accounts supported. A System Manager configures each sender's token, external phone ID, WABA/portfolio and enabled flag, plus the integration's application secret and verification token. Password fields stay encrypted at permission level 1. App users read sender labels/metadata without tokens.

Three independent System Manager switches default off: outbound requests, inbound capture and automation. A sender also defaults disabled. Tests never enable these switches on the development sites; their actual values are controlled by the site's administrator. Provider integration can be exercised with the isolated fixtures/mocked transport without any real sends. No public callback hostname, tunnel or production deployment is included.

The webhook endpoint is `/api/method/whatsapp_messaging.messaging.webhooks.receive`. Verification emits the exact challenge; POST verifies HMAC over the original bounded bytes, stores durable receipts before acknowledgement, handles batches/deduplication, and quarantines unknown accounts or repeated failures. Admin replay is explicit. Raw webhook payloads are System Manager-only. Site-wide CSRF protection is unchanged.

A running bench worker and scheduler execute durable jobs. A running bench Socket.IO service provides realtime push; the inbox's authorized polling also works without it. The implementation adds the fixed once-per-minute scheduler hook but does not change the bench Procfile or start new unattended production services.

## Installation, compatibility and validation

Run the normal app migration and `bench build --app whatsapp_messaging`; clear the asset manifest cache/restart long-lived development web processes after a new bundle is added. Standard workspace exports include current timestamps and are imported through normal migration, avoiding development-mode export side effects.

Migrations are additive and stop old app-generated encoded jobs. Legacy child history and standalone records remain preserved and read-only; they are not relabeled as delivered, attached to guessed accounts, or automatically resent. New canonical conversations use stable IDs, readable titles and explicit sender/peer identity. No automatic retention deletion is introduced.

The isolated test harness covers installation/migration, roles and generic APIs, queue/commit recovery, actual RQ execution with mocked transport, webhook HTTP/signatures/deduplication, receipt ordering, source/file permissions, private PDF transfer, schedules and campaigns. Browser verification uses fictional users/data in the disposable site, including desktop/mobile navigation, personal unread cards, assignment and draft preservation. See the current validation JSON for final counts and limitations. Live Meta/provider contracts and public ingress remain unverified and require a separately configured live environment.
