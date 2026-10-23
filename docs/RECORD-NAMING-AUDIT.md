# Record naming conventions

Checked the canonical Mac development app, `hms.localhost` and `development.localhost` on 18 October 2026. Both installed sites match the source naming definitions, with no Property Setter naming overrides or Document Naming Rules for this module. There are **24 DocTypes: 20 ordinary record types, 3 child tables and 1 singleton**. The reviewed naming plan is now implemented locally. The table retains the original audit for comparison; the new convention applies to new records. Existing record IDs are preserved.

## Original audit and implemented convention

The framework’s `hash` rule generates a 10-character ID. Conversation and Media controllers generate 20-character IDs instead. Child-table row IDs are internal; users identify those rows through their parent and displayed fields.

| DocType | Previous naming | New record naming | Display title example |
|---|---|---|---|
| Static Recipient | format:{label} | Keep the Label as the name | Reception coordinator |
| Static Recipient Link | Automatic 10-character child-row ID | Keep parent-managed internal row ID | Show selected recipient in the parent table |
| WhatsApp Approved Template | Automatic 10-character ID (hash rule) | WA-ATPL-000001 | appointment_confirmation · en |
| WhatsApp Attachment | Automatic 10-character ID (hash rule) | WA-ATT-2026-000001 | visit-instructions.pdf |
| WhatsApp Automation Run | Automatic 10-character ID (hash rule) | WA-RUN-2026-000001 | Appointment confirmation · Schedule · 19 Oct |
| WhatsApp Conversation | New canonical: 20-character generated ID; legacy: recipient value (controller overrides schema) | WA-CONV-000001 | Riverbend Patient Services · Meera Rao |
| WhatsApp Conversation Activity | Automatic 10-character ID (hash rule) | Keep internal ID | Conversation · action · actor · time |
| WhatsApp Conversation Field | Automatic 10-character child-row ID | Keep parent-managed internal row ID | Show message details in the parent table |
| WhatsApp Conversation Read | Automatic 10-character ID (hash rule) | Keep internal ID | Conversation · user |
| WhatsApp Identity Alias | Automatic 10-character ID (hash rule) | Keep internal ID | Contact · identity kind · value |
| WhatsApp Media | 20-character generated ID from controller | WA-MEDIA-000001 | Visit instructions |
| WhatsApp Message | format:{to}-{######}; to is not a field, so names appear as to-000023 | WA-MSG-2026-000001 | Outbound · Meera Rao · Delivered |
| WhatsApp Message Log | Automatic 10-character ID (framework fallback) | Keep historical IDs | Legacy source / message / date |
| WhatsApp Message Template | format:{template_name} | Keep Template name as the name | Appointment confirmation |
| WhatsApp Outbox | Automatic 10-character ID (hash rule) | WA-OUT-2026-000001 | WA-MSG-2026-000001 · Ready |
| WhatsApp Peer | Automatic 10-character ID (hash rule) | WA-PEER-000001 | Meera Rao |
| WhatsApp Phone Number ID | format:{label} | Keep the Label as the name | Riverbend Patient Services |
| WhatsApp Record Link | Automatic 10-character ID (hash rule) | Keep internal ID | Conversation · linked record |
| WhatsApp Schedule | Automatic 10-character ID (hash rule) | WA-SCH-000001 | Appointment confirmation · Daily 09:00 |
| WhatsApp Send Attempt | Automatic 10-character ID (hash rule) | WA-TRY-2026-000001 | WA-OUT-2026-000001 · Attempt 1 |
| WhatsApp Settings | Fixed name: WhatsApp Settings | Keep the fixed singleton name | WhatsApp Settings |
| WhatsApp Static Recipient | Automatic 10-character child-row ID | Keep parent-managed internal row ID | Show recipient in the parent table |
| WhatsApp Status Event | Automatic 10-character ID (hash rule) | WA-STE-2026-000001 | WA-MSG-2026-000001 · Delivered |
| WhatsApp Webhook Event | Automatic 10-character ID (hash rule) | WA-WHE-2026-000001 | Processed · received time |

## Findings from the original audit

- `WhatsApp Message` names use `format:{to}-{######}`, but the current schema has no `to` field. Canonical messages have therefore appeared as `to-000023` in isolated workflow tests. A clear message prefix is preferable to the missing-field expression.
- `WhatsApp Conversation` still declares recipient-based naming in JSON, but its controller assigns a 20-character ID when `identity_key` is set. The audit accounts for this runtime behavior.
- All 24 DocTypes currently have no configured `title_field`, so ordinary Link fields show record IDs rather than a friendly title. Some custom screens already display recipient/rule labels; this does not configure the standard Link fields.
- Sender accounts, local message templates and reusable recipients already use a meaningful user-entered name. These can retain that approach.
- A route beginning `new-whatsapp-phone-number-id-...` is an unsaved form’s temporary identifier. On save, the sender record uses its Label.

## Implemented behavior

1. Keep existing descriptive naming for configuration records: sender Label, local Template name and reusable-recipient Label.
2. Give user-facing operational records clear type prefixes and padded sequences, with a year for high-volume dated activity. The year is the creation year, and sequence values are generated by the framework.
3. Add display titles and useful search fields so users can find records by sender, recipient, template, file or source record while the permanent record ID stays stable. Show that title in Link fields and lists where appropriate.
4. Keep generated IDs for internal read cursors, identity aliases, record links, activity rows and child tables; show their related record and meaningful details in diagnostic views.
5. Preserve existing historical record IDs. Apply a new convention to new records and add readable titles to older records. Keep provider IDs, identity keys, request keys and duplicate-detection keys unchanged.

The table’s sample titles use the fictional hospital guide data; the naming prefixes themselves are independent of that scenario. The implementation preserves existing record names, provider IDs, identity keys, request keys and duplicate-detection keys. A post-migration patch backfills display titles without saving documents or changing their modified timestamps.

## Implementation details

- The 12 sequential types use framework naming series, with independent six-digit counters for each prefix. Dated series include the creation year and start a separate sequence each year. `WA-MSG-.YYYY.-.######`, for example, produces `WA-MSG-2026-000001`.
- Sender accounts, local templates and reusable recipients keep their descriptive names. All 20 ordinary record types have display-title and search-field metadata; child tables and the settings singleton retain their internal naming.
- Generated `Record Title` fields are read-only. Titles summarize existing record metadata and do not include message bodies, webhook payloads, credentials or file contents. Standard Link searches find both names and titles.
- Service writes update titles when the fields used by a title change. Correcting a contact display name also refreshes its existing conversation, message and identity-alias titles.
- New conversation and media records use their declared series; the old controller overrides have been removed. Existing legacy conversations retain their historical names and remain discoverable by recipient.
- Sequence names are permanent and cannot be manually renamed through standard record actions. Readable titles can change as the underlying details change.

Validation includes installation on both local sites, transactional record creation and rollback, old-name/key/timestamp preservation, title search, title updates and the existing integration workflows. See [validation results](validation/record-naming-2026-10-18.json).

## Shared field policy configuration added 20 October 2026

`WhatsApp Template Field Policy` uses its Source DocType as its permanent name (for example, `Patient`), with Source DocType as its display title and search field. It is a configuration record managed once for all templates of that source type. This adds one DocType to the original 24-type audit.
