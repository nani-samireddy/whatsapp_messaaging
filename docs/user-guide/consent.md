# Record consent or stop sending

Record appointment-message consent or stop sending to a patient.

**Who can do this:** Admin · System Manager

## What this workflow does

This records whether a recipient has agreed to receive messages and where that agreement was recorded. An Admin can also suppress a recipient to stop outgoing messages to them. The app checks consent and suppression when preparing and sending messages.

[All workflows](README.md)

## 1. Open the recipient’s thread

Confirm the recipient number in Details before changing eligibility.

## 2. Choose Update eligibility

Choose Update eligibility. Record Consent recorded only when the patient has given consent, and enter its source, such as Appointment booking form.

## 3. Suppress when necessary

Enable Suppress sending to stop outgoing messages to this recipient. Save the change.

## 4. Review the result

Details displays the updated eligibility and Activity records the change. Eligibility is checked again when dispatching a queued message.

## What to check

The recipient’s consent or suppression state is saved. Suppression blocks both normal replies and approved-template sends.

## If you need help

Editors can view the eligibility summary but cannot change it. Never record consent solely to bypass a blocked send.

## Screenshots

![Recipient eligibility dialog shown to Admin and System Manager.](../../whatsapp_messaging/public/docs/screenshots/recipient-eligibility.jpg)

Recipient eligibility dialog shown to Admin and System Manager.

## Related workflows

- [Use an approved WhatsApp template](approved-templates.md)
- [Check delivery and handle blocked sends](delivery.md)

Riverbend Hospital is a fictional training setting; no real patient data is shown. Updated 22 October 2026.
