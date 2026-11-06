# Production readiness

Reviewed 1 November 2026 on `feature/production-readiness`. Code validation and deployment acceptance are separate. This review does not publish a domain, deploy to the server, enable sending, copy credentials or send live messages.

## Findings fixed in this review

| Finding | Change | Regression coverage |
|---|---|---|
| Inbox attachment downloads bypassed the original business record's access check. | Recheck File and parent-record access, privacy and the saved content hash on download. | An agent with conversation access but no source-record access cannot download its PDF. |
| An attachment queued from a business record could upload after its sender lost source access. | Recheck file/parent permissions immediately before uploading. Newly uploaded, unattached files become message attachments; existing business files keep their original parent. | Revoked access holds a send without provider transport; normal shared Inbox uploads remain readable by permitted agents. |
| A slow worker could send after an expired claim was reclaimed, then clear the replacement worker's sender lease. | Lock and verify the claim owner, deadline and sender lease after upload, renew before the message request, and release only the owned sender lease. | Expired/superseded workers send nothing and preserve the replacement claim. |
| An HTTP timeout could overwrite a delivery/read receipt that arrived before the response. | Reconcile signed receipts for both successful and exceptional transport outcomes. | A committed Read receipt remains Read after a timeout; uncertain requests are not automatically retried. |
| Queued rule messages could retain an old recipient or old rendered values after a source edit. | Re-render the permitted source and compare recipient, message variables/body and attachment identity at dispatch. | A changed source phone or message value holds the prepared send. |
| Message/media POST requests could follow redirects. | Disable redirects for those authenticated provider requests. | Message and media calls explicitly disable redirects. |
| New document tests were outside the fresh-install/upgrade harness. | Include generic document fixtures and real PDF rendering with public assets served only over container loopback. | Generic document delivery runs in the internal-only harness; the HMS-specific invoice case runs separately. |

The new **WhatsApp Settings → Check setup** action is read-only and System Manager-only. On narrow layouts it is under the form's **Menu**. It checks schema, endpoint syntax, enabled sender credentials, webhook credentials, public HTTPS configuration, the three switches, recent scheduler execution and live queue-worker heartbeats. It returns no secrets, contact numbers, message bodies or queue payloads. A configured queue without a running worker is reported as blocked.

The result `configuration_ready` describes local configuration checks only. It does not prove that the token is accepted by Meta, the callback is reachable, every template is approved, or a recipient received a message. These remain explicit external checks in the result.

## Deployment preparation

1. Build a tested image containing this revision. Back up the target database, site configuration/encryption key and public/private files; preserve their matching image revision. Rehearse restoration on an isolated site.
2. Migrate the selected target site and build assets using the normal deployment process. Restart application processes so they load the same revision.
3. Configure the sender's numeric Phone Number ID/WABA ID and token, and the Meta App ID/App Secret/Verify Token. Enter secrets privately through the existing settings form or a hidden local prompt. Do not copy them into Git or the image.
4. Set `host_name` to the site's public HTTPS URL. Verify DNS, certificate, proxy routing, HTTPS headers and authenticated access. Keep databases, Redis and proxy administration private.
5. Configure the dedicated media queue while preserving the bench's other workers:

   ```sh
   bench --site YOUR_SITE execute whatsapp_messaging.messaging.media_cloud.configure_worker
   ```

   Restart web/worker processes after changing common bench configuration. Run supervised workers subscribed to **default** and **whatsapp_media**, plus the normal Frappe scheduler. A foreground `bench worker --queue whatsapp_media` is a diagnostic, not a persistent deployment service. In Docker, add that worker to Compose using the same app image and sites volume, and include it in updates, graceful stops and backups. The existing deployment scripts do not gain a media worker merely by copying app code.

6. Enable the target site's scheduler through the normal administration process, start its scheduler service, and allow a tick to execute. Check timezone and server clock. A running container alone does not establish that this site is enabled or its jobs are executing.
7. Review/import templates, shared-field permissions, sender selection, hospital record/phone mappings, recipient consent, document rules, flow versions and schedules. Code deployment does not transfer configuration records from the development database.
8. Keep outbound/automation off while reviewing previews. Enable only the selected environment and workflows for the acceptance test. Run the read-only check again:

   ```sh
   bench --site YOUR_SITE execute whatsapp_messaging.messaging.readiness.check
   ```

## Required acceptance on the deployment

- HTTPS login, editor/admin/System Manager permissions, private file restrictions and realtime/polling recovery.
- Meta callback verification and signed inbound/delivery events at `/api/method/whatsapp_messaging.messaging.webhooks.receive`. Confirm the correct WABA subscription and sender mapping.
- One opted-in test contact receives an approved template, sends a reply, and receives a private image and PDF. Check Delivered/Read separately from Accepted.
- Patient creation produces one welcome. Follow-up and OP-validity reminders run at **09:00 Asia/Kolkata**, **two days before, one day before and on the due date**, without manual scheduler ticks or duplicate sends.
- The hospital menu and staff handoff work. Appointment lookup returns only the current WhatsApp contact's most recently created Scheduled appointment; another phone cannot retrieve its details.
- A reviewed document passes any staff-release requirement, generates/uses the correct private PDF, and goes to its mapped contact. Editing the source, approval or recipient holds stale queued work.
- Repeating a webhook, restarting a worker during upload/request, an expired token, rate limiting, a closed reply window and a source-access revocation produce safe, understandable states. Never automatically resend Unknown or already-accepted requests.
- Exercise inbound attachment downloads and larger recipient batches with controlled fixtures before relying on them at scale. Previous live acceptance covered a small opted-in test audience.
- Check approved reminder/document wording and actual Meta review/rejection outcomes. Text templates and imported DOCUMENT-header templates are supported; audio/video/stickers and other unsupported Meta formats are not silently accepted.

## Operations

Review Outbox **Unknown/Held/Failed**, failed or quarantined webhook events, failed flow/document preparation, worker heartbeats and scheduler evidence. Preserve backups, restrict access to message/answer history and private files, and define the hospital's retention policy. There is no new automatic history deletion or credential rotation in this change.

The Mac-local check during this review found a development hostname, no recent scheduler evidence, and no live default/media-worker heartbeats. Those are launch blockers for that environment, not instructions to start live sends automatically. The server was not inspected or changed by this review.

## Validation evidence

See [review results](validation/production-readiness-2026-11-01.json) for fresh-install, legacy-upgrade, HMS document, local Python and JavaScript results. Provider HTTP calls are mocked; the fresh-install and upgrade networks have no external route. The separate HMS document suite blocks Requests transport and uses only its explicitly named local test site.

See [DocType naming review](DOCTYPE-NAMING-REVIEW.md) for all 36 DocTypes. No DocType/record IDs have been renamed by this review.
