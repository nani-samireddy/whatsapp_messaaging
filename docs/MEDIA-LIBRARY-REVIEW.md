# WhatsApp Media review and changes

Reviewed and updated on the Mac development stack, 21 October 2026.

## Findings

The previous form exposed both URL and Upload sources, audio/video/sticker types, editable MIME types and provider media IDs although the current send pipeline accepts private JPEG/PNG/PDF files only. Its controller performed no validation. Consequently saved type/title metadata could be wrong, and errors appeared only later while selecting a template. Quick Entry exposed nearly every field and did not run the full form's uploader configuration. The native Attach control also saved immediately after uploading on an existing form and deleted the stored File when clearing it.

Media now uploads to WhatsApp Cloud after the record is saved. Captions on templates come from the template's message text, not the library's old Caption field.

## Resulting form and lifecycle

- Quick Entry contains optional **Label**, required **Sender** and **File**, and an automatic private preview with type and size. The label defaults to the filename on Save. The same entry works when created from a template's Media link.
- The full form has Label, Sender, File, preview, readonly File Details, WhatsApp Cloud status/results, and optional internal Notes. Generated Record Title is used in links, with no duplicate editable input. Notes preserve the old Caption data but are not sent as message captions.
- Source mode remains a hidden compatibility field. Old URL records retain a readonly Legacy Source section. New URL-only records are rejected.
- Both entry points configure private uploads, supported file filters and visible file-size guidance. The browser's image optimization controls remain available. Server checks enforce privacy, file permissions, bounded actual bytes, image/PDF validity and size; client metadata is never authoritative.
- After choosing a file, a read-only inspection request fills its format, size and preview. Stale responses cannot overwrite a later file choice. **Save** waits for inspection, repeats the server checks and derives the filename, MIME type, image/document kind, hash, checked time and status. It queues a cloud upload after the transaction commits; no message is created or sent.
- New uploads remain private and unattached until the explicit media Save. Saving binds only the current user's unattached upload to the library record; files already attached to a business record are never moved. That makes new library uploads reusable by permitted app roles while preserving business-record access checks.
- Replacing a selection updates all derived details and clears obsolete provider IDs. Removing a selection clears those details without deleting the File or auto-saving. Saving an existing empty record marks it **Needs File**. Only **Ready** assets are offered by the template picker; runtime preparation validates the actual file again.
- Deleting a library record detaches its stored Files rather than deleting message history or queued attachment files. Physical file deletion is an explicit File Manager action. Queued sends retain their prepared file snapshots; later library edits affect future preparations.

## Existing records

The patches preserve record names, original URL values, modified timestamps, stored File rows, file privacy and template records. They recalculate metadata for valid private files, mark URL-only records **Legacy URL**, mark unverifiable existing files **Needs Attention**, and initialize cloud status without uploading anything. Existing valid files require selecting a Sender and saving or choosing Upload / Retry. Existing invalid files require a supported private replacement. Migration never fetches a URL, sends a message, changes a credential or privatizes a public file.

## Cloud upload

Both **Enable Outbound Requests** in WhatsApp Settings and the selected Sender must be enabled. Otherwise the local file is saved with an actionable **Blocked** status. An older record with no Sender shows **Needs Sender**. Uploading does not require turning on automation.

The dedicated `whatsapp_media` queue runs uploads separately from message dispatch. Status progresses from **Pending** through **Uploading** to **Uploaded**, with Meta's Media ID and upload time. **Failed** has a safe error message and an **Upload / Retry** action. Token errors explain how to correct the token without retaining provider bodies or credentials. The worker rechecks the requesting user's enabled state, app role, document/file permissions, source hash, sender and global switch immediately before uploading. A lease prevents duplicate active jobs; stale job generations cannot overwrite a replacement's results. The normal scheduler sweep can recover expired leases, and Retry provides manual recovery.

Meta uploads expire, so the app treats IDs as refreshable rather than permanent. It refreshes on a later Save or explicit refresh after 29 days. Message dispatch reuses an unexpired ID only for the same sender, content hash and readable library entry; otherwise it performs its existing bounded upload. Deleting a library entry retains stored files and does not call Meta's delete endpoint. [Meta media documentation](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media).

### Worker setup

From the bench root, configure the queue while preserving other workers:

```sh
bench --site YOUR_SITE execute whatsapp_messaging.messaging.media_cloud.configure_worker
bench worker --queue whatsapp_media
```

For a managed deployment, add that dedicated worker command to the process manager and restart web workers after changing common bench configuration. Configuration alone does not turn on outbound requests or upload existing files. If the queue is not configured, saves show **Blocked** instead of failing after commit. On the Mac development stack only this media worker is started; unrelated message queues are not consumed.

## Verification

The prior 109 Frappe integration checks and 26 local checks pass. Thirteen additional library tests cover metadata tampering, defaults, type correction, replacement/removal, retained files, Quick Entry schema, invalid uploads, actual size limits, roles, shared library access, business-file parent preservation, deletion and migration. Sixteen cloud checks cover after-commit Redis queuing, settings, actor/sender checks, successful uploads, safe failures, retry, duplicate leases, source replacement and ID-cache boundaries. Provider transport is mocked in the isolated test network; this does not claim a live Meta upload. Browser checks cover private uploads, explicit-save behavior, automatic image-to-PDF metadata updates and cloud status display. The user guide includes a dedicated workflow and fictional Riverbend Hospital screenshots.
