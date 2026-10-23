# Template content and shared fields

Templates now own reusable content and Meta review. Campaigns reference them and own recipient mappings, filters, events and schedules. See [Templates and campaigns](TEMPLATES-AND-CAMPAIGNS.md) for authoring, rejection guidance and migration behavior.

Type is automatic and read-only. A template without Media uses `text`; a private JPEG/PNG uses `image`; a private PDF uses `document`. The server reads the actual file bytes and checks access, privacy and size on preview, save and message preparation. Removing Media restores `text`. Text accompanying an attachment becomes its caption. Supported Meta-approved templates use their approved text-body format and cannot be combined with Media in this version.

WhatsApp Media uploads start as Upload and default to Private. The upload dialog accepts JPEG, PNG and PDF and does not offer a Public toggle. Selecting an existing public library file still requires a new private upload; the app does not silently change an existing file's visibility or public links. Media URLs and unsupported content show a clear error.

New media records require a Sender. Saving queues their WhatsApp Cloud upload after commit when Outbound Requests and the Sender are enabled. The record displays the upload status and returned Media ID. Sending can reuse that ID for the same sender and file while fresh, with the existing send-time upload as a fallback. No message is sent by saving a media record. See [Media library workflow and worker setup](MEDIA-LIBRARY-REVIEW.md).

## Shared source-field approvals

A System Manager opens **WhatsApp Administration → Template Field Policies**, creates or opens a policy for the source DocType, checks the fields to permit and saves. The policy name is the source DocType, such as `Patient`. The searchable field picker shows readable business fields; hidden fields, passwords and fields named like tokens or secrets are excluded. Actual source-record and field permissions are also checked whenever a message is prepared.

Every template using that DocType inherits the same approvals. Template forms use a searchable Insert field menu and a shared configuration shortcut; there is no per-template JSON field to edit. The message editor only offers the shared approved fields. Positional mappings for a Meta-approved message must refer to those fields as well.

Existing valid template approvals are combined by source DocType during migration. The old per-template column is kept as a hidden compatibility snapshot, while the shared policy is authoritative. Migration is idempotent and never re-approves a field that an administrator later removes. Changing or deleting a policy updates the relevant template versions so queued sends and campaign snapshots based on older rules must be reviewed. The change does not activate automation or replace its execution user.

Existing Whatsapp Admin and Whatsapp Editor roles can read the shared configuration. System Manager manages approvals, matching the previous authority for source-field approvals. No new login or role is required.

## Local validation

Both Mac sites were backed up and migrated. Tests cover actual image/PDF bytes, read-only Type, saved-value tampering, media removal, public/unsupported/URL media, field-policy inheritance, role permissions, and queued rule invalidation. Browser tests cover shared checkbox save/revocation, the inherited editor fields and automatic Type. Updated workflow screenshots use fictional Riverbend Hospital data in a disposable test site.

## Inline editor and live preview

Write directly in **Message Text**; no popup or Apply step is required. Selecting Media changes the same field to **Caption**, preserving its content. Removing Media restores Message Text. A side-by-side, theme-aware preview updates while typing, shows a private image thumbnail or PDF card, and displays approved placeholders as named chips. Unknown or revoked placeholders are marked for review. This is a layout preview, not a fetch of patient data or a guarantee of Meta delivery. Saving still uses the native form control and existing permissions.

**Insert field** offers the source record, Template labels, and every readable, persisted Single DocType as a **Static** source. Pick a source, search for a field, and click to insert it at the cursor. An empty static source remains available with a shortcut to its shared field policy. Virtual reports and arbitrary linked records are not static sources.

Static placeholders use `{{static.hospital_settings.hospital_name}}`, with a unique namespace derived from the installed DocType name. Only explicitly approved eligible fields resolve, as the execution user, with current document and field permissions. Static field access is checked again before dispatch. Values are not returned to the editing UI. A static policy applies across all templates and its revocation changes the version of templates referencing it, holding already-queued sends and stale campaign previews. Existing source placeholders continue to work unchanged. No static fields are approved automatically during migration.

## Optional header and footer

Compose Message includes fixed text Header and Footer fields (60 characters each). Preview and sending include them in both modes. Local messages add the sections to the body or media caption; Meta mode registers separate text components. See [Templates and campaigns](TEMPLATES-AND-CAMPAIGNS.md#header-and-footer).
