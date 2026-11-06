# DocType naming review

Reviewed 1 November 2026 against the current application source. There are **36 DocTypes: 27 ordinary record types, 8 child tables and 1 singleton**. The plain-language changes below are implemented in the local source. The migration preserves record IDs and existing links.

## Full inventory

| Previous / retained DocType | Type | Current name / decision | Purpose / reason |
|---|---|---|---|
| Static Recipient | Record | **Additional Numbers** (applied) | A reusable, manually maintained recipient; keep separate from an actual WhatsApp contact. |
| Static Recipient Link | Child table | **Additional Number Entry** (applied) | Child row selecting a saved recipient. |
| WhatsApp Approved Template | Record | **WhatsApp Meta Template** (applied) | Meta catalogue entry with any review status, including pending and rejected. |
| WhatsApp Attachment | Record | Keep | Private file associated with a particular message. |
| WhatsApp Automation Run | Record | Keep | One execution of a campaign, schedule, document event or manual send. |
| WhatsApp Campaign | Record | Keep | Audience, phone mapping, record-event triggers and date-reminder rules. Keep Campaign to preserve the agreed templates/campaigns separation; describe its trigger role in the UI. |
| WhatsApp Conversation | Record | Keep | Inbox thread between one sender and one contact. |
| WhatsApp Conversation Activity | Record | Keep | Assignment, consent, linking and other conversation audit actions. |
| WhatsApp Conversation Field | Child table | Preserve; mark legacy | Old embedded conversation/message rows, retained for history. |
| WhatsApp Conversation Flow | Record | Keep | Published menu/chat workflow configuration. |
| WhatsApp Conversation Read | Record | Keep internal name; display Inbox Read State | The agent’s inbox read cursor, not a Meta delivery/read receipt. |
| WhatsApp Document Condition | Child table | Keep | Child row specifying an additional document-delivery condition. |
| WhatsApp Document Delivery | Record | Keep | One source document’s preparation, release and sending record. |
| WhatsApp Document Parameter | Child table | **WhatsApp Document Variable** (applied) | Align with the existing Template Variable terminology. |
| WhatsApp Document Rule | Record | **WhatsApp Document Delivery Rule** (applied) | Trigger, recipient, message mapping and PDF-delivery configuration. |
| WhatsApp Flow Choice | Child table | Keep | Child row representing a menu option and destination. |
| WhatsApp Flow Event | Record | Keep | An incoming message’s flow-processing event. |
| WhatsApp Flow Session | Record | Keep | One conversation’s flow state and collected answers. |
| WhatsApp Flow Step | Child table | Keep | Child row representing one action in a conversation flow. |
| WhatsApp Identity Alias | Record | Keep | Internal mapping from a provider identity to a contact. |
| WhatsApp Media | Record | Keep | Reusable private media library and its Meta upload status. |
| WhatsApp Message | Record | Keep | Canonical incoming or outgoing message. |
| WhatsApp Message Log | Record | Preserve; mark legacy | Earlier message log, retained for history. |
| WhatsApp Message Template | Record | Keep | Reusable local content and Meta-template variable mappings. |
| WhatsApp Outbox | Record | Keep | Durable sending request and dispatch/retry state. |
| WhatsApp Peer | Record | **WhatsApp Contact** (applied) | Canonical person/recipient identity, consent and message blocking. |
| WhatsApp Phone Number ID | Record | **WhatsApp Sender** (applied) | Sending number, credentials and WhatsApp business account configuration; the ID is only one field. |
| WhatsApp Record Link | Record | Keep | Internal connection between a conversation and a business record. |
| WhatsApp Schedule | Record | Keep | One-time or recurring sending schedule. |
| WhatsApp Send Attempt | Record | Keep | One actual provider-request attempt for an outbox item. |
| WhatsApp Settings | Singleton | Keep | Singleton integration settings and safety switches. |
| WhatsApp Static Recipient | Child table | Preserve; mark legacy | Old recipient snapshot rows on messages; not the saved-recipient master. |
| WhatsApp Status Event | Record | Keep internal name; display Delivery Status Event | Provider sent/delivered/read/failed event. |
| WhatsApp Template Field Policy | Record | **WhatsApp Template Fields** (applied) | Shared administrator approval of fields available to message templates. |
| WhatsApp Template Variable | Child table | Keep | Child row mapping a template body variable. |
| WhatsApp Webhook Event | Record | Keep | Signed incoming webhook receipt and processing status. |

## Applied business-name changes

1. WhatsApp Phone Number ID → **WhatsApp Sender**.
2. WhatsApp Peer → **WhatsApp Contact**.
3. WhatsApp Approved Template → **WhatsApp Meta Template**. Approval remains a status, not part of the type name.
4. Static Recipient → **Additional Numbers**, with child type **Additional Number Entry**.
5. WhatsApp Document Rule → **WhatsApp Document Delivery Rule**.

Keep **WhatsApp Message Template** and **WhatsApp Campaign** separate. Do not merge their responsibilities. A saved recipient is a configured recipient entry; a contact is the canonical identity with consent and conversation history.

Internal state and audit types do not need broad renaming. Improve displayed field/menu labels where helpful. Preserve historical log/child types and remove them from normal navigation rather than moving their data into a competing history model.

## Safe migration requirements

- Back up the site and validate a fresh install plus an upgrade with existing conversations, files, flows and queued work.
- Update DocType packages/controllers, Link and Dynamic Link targets, permissions, fixtures, navigation, Python imports, RPC routes, tests and help pages together.
- Preserve record IDs, provider IDs, unique identity/request/event keys and retained historical data. Never recreate queued sends during a naming migration.
- Review legacy stored method paths and external callers; document compatibility and any route changes.
- Validate pending/claimed/accepted/unknown sends and signed webhook reconciliation after the migration. Renaming must never make an uncertain send eligible for an automatic resend.
- Do not rename existing record series such as WA-MSG or WA-OUT just to match a clearer display name.

The earlier RECORD-NAMING-AUDIT.md describes the original 24-type record-ID migration, not the current full DocType inventory.

## Plain-language interface

Forms, menus, buttons and help use the same terms: Sender, Contact, Record Type, Additional Numbers, Template Fields, Sending Queue and Delivery Updates. Form introductions explain what each record does. Campaigns use Pause This Campaign; settings explain sending, incoming updates and automatic messages separately. Flow steps say Show a menu, Ask a question and Pass to reception while keeping their stored values unchanged.

System-generated types retain their internal names; their menus, labels and descriptions use plain language. Raw identifiers, hashes and message data are grouped in a collapsed Technical Details section. Legacy history types remain unchanged.

The pre-model-sync patch is `whatsapp_messaging.patches.v1_0.plain_language_names`. It renames tables and metadata, moves encrypted sender credentials, updates Inbox link keys, and retains record names, child fieldnames and sending states. It refuses conflicting destination types rather than merging records. Run a site backup before migrating. REST clients must use the new DocType names; old DocType resource URLs are not aliases.

Validation: fresh install **271 passed, 2 skipped**; upgrade from `04ad660` **272 passed, 1 skipped**; 77 Python and 18 JavaScript tests passed. The Mac-local site was backed up, migrated and checked against pre-migration record and credential hashes. Navigation updates retain workspace layout and visibility.

## Runtime restart after migration

Restart every process that imports the app after deploying these names: web, default and media workers, and any Mac-local flow/document dispatch helpers. A web process started with `--noreload` retains old Python code even after files change and metadata caches are cleared. Traceback source lines can then show the new name while the running code still queries the old table. Use graceful worker shutdown, wait for active work to finish, then start replacements from the bench sites directory. Verify the actual authenticated workspace after restart; a fresh CLI process alone does not prove the running web process is current.
