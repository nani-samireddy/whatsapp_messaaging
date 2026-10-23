# Check delivery and handle blocked sends

Check whether patient messages were queued, blocked or delivered.

**Who can do this:** Editor · Admin · System Manager

## What this workflow does

This shows what happened to messages after they were queued, helping you find delays and failures. You can check whether a request is waiting, blocked, accepted by the provider or delivered, and review any available reason for a problem. The available controls let you cancel eligible unsent requests or retry confirmed unaccepted failures.

[All workflows](README.md)

## 1. Find the request

Use the conversation timeline or Campaign Runs → View details. Admin and System Manager can also open Administration → Outbound Queue and Send Attempts.

## 2. Read the status

Ready or Queued is waiting; Accepted is acknowledged by the provider. Sent, Delivered and Read follow receipts. Held means a precondition needs review; Retry wait is waiting for a bounded retry.

## 3. Handle confirmed failures

Review the reason and fix the issue first. Retry confirmed failure is available only for a known unaccepted failure. Cancel send applies only to eligible requests before a network attempt starts.

## 4. Treat Unknown carefully

Unknown means the provider outcome is uncertain. Review receipts and history before deliberately composing a new message. The same uncertain request is not retried automatically.

## What to check

You know whether work is queued, blocked, accepted or actually delivered. Run totals separate record expansion from send outcomes.

## If you need help

Editors can inspect their permitted run details; campaigns and administration diagnostics require Admin or System Manager. For delayed work, ask your System Manager to check switches, sender state, scheduler and workers.

## Screenshots

![Automation run results show each request’s state and a link to its conversation.](../../whatsapp_messaging/public/docs/screenshots/delivery-results.jpg)

Automation run results show each request’s state and a link to its conversation.

## Related workflows

- [Reply to a message](replies.md)
- [Configure and run a campaign](campaigns.md)
- [Review inbound and webhook issues](webhooks.md)

Riverbend Hospital is a fictional training setting; no real patient data is shown. Updated 22 October 2026.
