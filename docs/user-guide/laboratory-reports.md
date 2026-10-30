# Send a reviewed laboratory report

Send the patient’s completed private PDF after clinical review and explicit staff release.

**Who can do this:** Clinical staff for review · Admin or System Manager for messaging release

## What this workflow does

The HMS - Released laboratory report preset watches Lab Report → Status = Reviewed, resolves the linked patient’s Mobile number, and uses the private PDF in Report file. It requires an additional messaging release. A reviewed status alone does not send the report.

[All workflows](README.md)

## 1. Prepare the hospital sender and consent

Configure the sender, obtain approval for a report-notification template with a Document header, and Sync approved templates on the sender. Check the patient’s country-code phone number and recorded messaging consent. Keep the preset disabled during setup.

## 2. Open the laboratory preset

Open WhatsApp Document Rule → HMS - Released laboratory report. Set Record type to Lab Report, Trigger to Field changes to a value, and Trigger field to Status.

## 3. Select Reviewed and keep the release step

In Send when value is, type /Reviewed and choose Reviewed as a chip. Keep Require staff release before sending checked. For the existing preset these values are already selected. Only when conditions can further narrow the rule; every added row must match.

## 4. Map the linked patient and actual PDF

Choose A linked record → Patient → Mobile. Set Document source to Private attachment and Attachment field to Report file. Select the configured Sender and Approved document template, then map each body variable. Use the actual completed result PDF attached to this Lab Report.

## 5. Save, preview and enable the rule

Save and Preview a readable source report. The preview checks configuration without creating a PDF or sending. Complete template approval and mappings, then enable the rule and required WhatsApp integration switches. A worker must be available.

## 6. Complete the source report and clinical review

In Lab Report, attach the completed private PDF to Report file and fill Received On. HMS requires both the received date and private file for Received or Reviewed reports. Clinical staff review the results and save Status = Reviewed. Configure the rule before this transition; previously reviewed reports are not automatically backfilled.

## 7. Release the matching delivery

Open the rule’s Delivery history, then the matching WhatsApp Document Delivery in Awaiting release. A Whatsapp Admin or System Manager with write access to the source report checks the patient, current report and PDF, then chooses Release document. The worker prepares the attachment and queues the approved message.

## 8. Check the patient delivery outcome

Check Message status or View message delivery for accepted, delivered, read, failed, held or unknown outcomes. Preparation status alone is not proof of patient delivery. If held, correct the stated issue before using the appropriate retry action.

## 9. Handle existing or changed reports deliberately

An enabled rule’s Prepare current document action can create a delivery for an eligible existing source version, subject to the same release requirement. HMS protects reviewed report status, file and review details. Do not alter them to force a send. Changed source/rule versions and uncertain provider outcomes require review; do not repeatedly create new messages.

## What to check

The source Lab Report is clinically reviewed, its completed PDF is private and belongs to that report, the linked patient’s phone is correct, and staff release is recorded before sending. Verify the actual delivery outcome in the message log.

## If you need help

Clinical authorization to review a result and WhatsApp authority to release a document are separate permissions. The preset’s Test number sender label is local configuration; choose the hospital’s configured sender and approved document template before enabling. A blank laboratory worksheet is not a completed result report.

## Screenshots

![The laboratory preset matches Reviewed and requires staff release before sending.](../../whatsapp_messaging/public/docs/screenshots/document-lab-trigger.png)

The laboratory preset matches Reviewed and requires staff release before sending.

![The linked Patient supplies Mobile, while Private attachment uses Report file.](../../whatsapp_messaging/public/docs/screenshots/document-lab-attachment.png)

The linked Patient supplies Mobile, while Private attachment uses Report file.

## Related workflows

- [Send documents automatically](document-delivery.md)
- [Record consent or stop sending](consent.md)
- [Configure a sender and integration](senders.md)
- [Check delivery and handle blocked sends](delivery.md)

Screenshots show local development screens. Available fields, values, sender accounts and actions depend on your site configuration and permissions. Updated 30 October 2026.
