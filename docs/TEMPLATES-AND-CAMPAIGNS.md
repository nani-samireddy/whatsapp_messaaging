# Templates and campaigns

Templates own reusable content, source-field mappings, optional local media and Meta review. Campaigns reference a template and own recipients, source filters, sender and manual/event/scheduled/bulk configuration. Multiple campaigns can share one template. Existing template names remain valid; the migration creates campaigns with the same names and preserves execution users and sending configuration.

## Authoring and review

Saving never submits to Meta or sends a message. Choose Local message or Meta-approved template. Meta mode supports text bodies, positional variables, fictional review examples, Utility/Marketing category and optional fixed text header and footer. Import existing supported Meta content into the same editor; map numbered variables using the shared field picker. Local media remains private and uses the existing media workflow. Meta media headers, header variables, buttons, authentication templates and named parameters is outside this implementation.

Admins and System Managers can explicitly submit saved content, edit a rejected template and check status. Editors can draft content and configure campaigns. Provider approval, content identity, WABA, field approvals, source access and recipient eligibility remain authoritative at send time.

Signed `message_template_status_update` webhooks retain the actual rejection code, explanation and recommendation where supplied. The form separates these from app guidance. Unknown reasons direct users to WhatsApp Manager or Business Support Home. HTTP/authentication errors are action failures, not Meta review rejections. Secrets are removed from stored error details.

Submission state is persisted before HTTP. Ambiguous results are never automatically resubmitted. Check status first. If a complete catalogue check still finds no matching name/language after ten minutes, the UI permits another explicit submission and explains that no request was resent. Creation retains the unique Meta name. A changed or rejected draft cannot use a prior approval.

## Selective import

On a saved Sender, Sync approved templates fetches the Meta catalogue and opens a searchable selection dialog. All review statuses appear with language, category and an expandable message preview. Choose a Source DocType and import up to 100 selected supported entries. Existing records are linked and preserved, including local edits; repeating an import does not create duplicates. Unsupported or unavailable entries are explained and cannot be selected.

Imports create inactive content records only, preserving fixed headers, bodies, footers, language and category. Numbered variables start with blank source mappings; users must configure these explicitly. Imports do not create campaigns, submit wording to Meta or send messages. Only Admins and System Managers can sync and import. Server validation rechecks sender access, WABA, current format, source access and creation permission. Catalogue row locks serialize concurrent imports across Senders sharing a WABA.

## Header and footer

Header and Footer are optional fixed text fields in Compose Message, each limited to 60 characters on one line. Body variables remain supported through the shared field picker. The live preview, campaign summary, bulk preview, Inbox template dialog and saved message history include the framing. Meta submissions use separate HEADER (TEXT), BODY and FOOTER components. Static headers and footers need no send-time parameters.

Local text messages and media captions include the sections as paragraphs. The complete local message must fit 4,096 characters; a media caption including framing must fit 1,024. Changing a saved header or footer invalidates prepared versions and requires Meta approval again. Imports preserve supported fixed text components; media headers, header variables and buttons remain unavailable.

## Campaigns and existing work

New campaigns start Disabled. Manual record actions, events, schedules and bulk previews use the campaign's configuration and current shared content. Automation Run, Schedule and Outbox references use a dynamic Campaign link; legacy APIs retain compatible template resolution.

The migration copies existing configuration without sending, changing execution users, enabling switches or starting workers. Existing canonical Meta body/mappings are copied into content; previously unused local text is retained in a hidden backup field. Existing names and source timestamps remain intact. Legacy pending previews and outbox intents may be held because their saved version predates the new combined campaign/content version. Review and prepare them again deliberately; never automatically replay them.

Edits to either campaign or template invalidate older prepared versions. Schedules use current content when preparing future occurrences; pausing prevents future work but cannot recall an HTTP request already in flight. Provider approval/eligibility checks still apply to queued work.

## References

- [Template components and text limits](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/components)
- [Meta template API](https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/whatsapp-business-account/message-template-api)
- [Template review and rejection guidance](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review)
- [Template management and editing](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-management)
- [Signed template status updates](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/message_template_status_update)

## Validation

Run `tests/integration/run.sh` in the internal disposable Compose environment and `python3 -m unittest discover -s tests -v`. Provider requests are mocked. Browser guide fixtures are fictional Riverbend Hospital records. Local development migration and browser evidence are recorded in `docs/validation/templates-and-campaigns-2026-10-21.json`.
