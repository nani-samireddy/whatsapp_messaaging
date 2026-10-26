# Conversation Flows

Admins create flows under **WhatsApp Templates & Automation → Conversation Flows**. Editors can preview flows and use Inbox takeover controls. The hospital starter stays a draft until its sample information is replaced and an Admin chooses **Publish and enable**.

The current release supports menus (reply buttons or lists), questions with text/date answers, consecutive messages, saved text templates, staff handoff and endings. It collects appointment requests for staff confirmation. It does not create or confirm HMS appointments. A configured template step can find an existing readable record that matches the WhatsApp contact and explicit filters.

## Workflow map

The editor uses locally bundled [Drawflow](https://github.com/jerosoler/Drawflow) 0.0.60 (MIT; provenance and licence in `public/vendor/drawflow`). Each menu choice has its own output connector. Drag a dot onto another card to connect it, or click a branch for an existing destination or a new connected step. Drag cards to arrange; use Undo/Redo, zoom, Fit, Expand or Auto arrange. Step list remains available.

The adapter persists canonical step keys, choice keys and validated `layout_json` positions, never Drawflow HTML or executable expressions. Moving cards does not change reply order or a published version. Saved positions survive reload; Auto arrange resets them. Repeated destinations share one card. Missing destinations and disconnected draft steps remain visible for repair.

## Template steps and record data

Choose **Template**, select a saved text template and choose its data source:

- **Flow values:** map every template variable to an earlier collected answer, the contact name, contact phone number or fixed text. Publishing requires each referenced answer on every incoming path.
- **Record lookup:** use the template's Source DocType; select a direct phone field or one linked record's phone field. This match always uses `contact.phone_number`, the actual sender of the incoming WhatsApp message. Add up to ten AND filters using readable fields, comparisons and collected answers/contact values/fixed text. No Python, SQL or Jinja is evaluated.

For Appointment Confirmation, first ask whether `+{{contact.phone_number}}` is the registered hospital number. **Yes, this number** leads to lookup. **No, enter number** leads to a **Phone** question, saving `registered_phone`. The question accepts a country code with optional spaces, brackets and hyphens, then stores international digits. Its matching-number path can continue to lookup; a different number follows **Different registered number** to a help message explaining that appointments can only be shown for the number the person is messaging from. A different entered number never triggers a record lookup. The person can message from their registered number or ask reception to update their registration. Both destinations are visible and editable in the canvas. No other phone number can be used to retrieve appointments in this flow.

The appointment lookup uses **Patient Appointment**, **Patient → Mobile** (`patient.patient_phone_number` on this HMS site), **Status = Scheduled**, and **Which matching record should be used? → Most recently created**. No date question or appointment-date filter is used. Selection orders by creation time descending, then record ID descending for a tie. It ignores last edit time and excludes records outside the phone/status filters. The default **Require a single matching record** rule remains available for other flows. Two linked contacts sharing a phone number still count as ambiguous and go to staff, even when the record rule is Most recently created. No match goes to reception. The flow does not create a booking or turn a request into a confirmed appointment. A newer matching booking before dispatch holds the stale queued confirmation for review.

Phone matches currently accept international digits or +digits; normalize stored phone numbers first. Single/child/virtual DocTypes and sensitive/hidden/unreadable fields cannot be used for record lookup. Shared template field policies still control which record values can appear in the message. Querying and rendering run as the publishing user; record access, contact match, filter results, rendered values and template approval are rechecked before dispatch. Changed content, approval or matching details hold the queued reply for review.

Only text templates are supported in flow steps. Meta templates must be approved for the flow's WhatsApp business account before publishing and require recorded contact consent. Local message templates use the open reply window. Header/footer are reused. A template edit requires reviewing and republishing linked flows. **Try flow** lets you simulate one/no/multiple records using fictional values; it never queries patient records or sends messages.

## Runtime

- `flow_engine.py` validates bounded graphs, renders explicit answer tokens and advances a pure state machine. No Python or Jinja runs from a flow; record lookup is a separate permission-checked service with explicit fields and filters.
- `flows.py` publishes immutable snapshots and processes durable Flow Events in incoming-message sequence under the conversation lock. Draft edits leave the running snapshot unchanged. Publishing is serialized by business number; only one flow can run per number.
- Signed incoming webhooks store readable menu-selection text and the opaque option ID. Each session's options are bound to its current step, version and reply generation. Replays, stale options and older incoming messages are skipped.
- Flow replies use the existing Outbox, provider pacing, uncertainty handling and delivery receipts. Dispatch rechecks the current publisher's permissions, published version, session generation, sender, recipient block and 24-hour window.
- Sending, Inbound and Automation must be enabled in WhatsApp Settings. Run the normal default worker and scheduler; `messaging.setup.tick` recovers queued/paced sends and pending flow events. Messages received with automatic replies disabled are skipped rather than backfilled when enabled. For this Mac-local bench, `scripts/run_local_flow_dispatcher.py --site hms.localhost` runs from the sites directory using the bench Python; it checks only flow events and flow replies every five seconds, leaving other scheduling to the normal scheduler.
- Assignment or a manual Inbox reply pauses a session and invalidates waiting automatic replies. Handoff leaves staff in control. **Allow menu requests** waits for the contact to request the menu again; it sends nothing immediately.
- Answers are retained in the session and processed-event snapshot. Staff can read them through **Flow details**. Failed preparation is recorded without copying exception text or credentials.

## Limits and verification

A flow supports up to 60 reachable steps, 200 total choices and 10 choices per menu. Three short options use reply buttons; longer/larger menus use a list. Text questions accept up to 200 characters; dates require YYYY-MM-DD and today or later. Phone questions require a valid international number and an explicit help destination for a number different from the WhatsApp contact. Three invalid answers hand off, and an hourly turn limit stops runaway replies.

`Try flow` uses the same pure engine without creating messages, sessions or outbound intents. Source tests are `tests/test_flow_engine.py`; network-isolated Frappe tests are `tests/integration/check_flows.py`. See [the user workflow](user-guide/conversation-flows.md).

Provider format references: [Meta interactive messages](https://www.postman.com/meta/whatsapp-business-platform/request/0v36tbh/send-reply-to-list-message) and [Meta SDK interactive object examples](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/messages/interactive/).
