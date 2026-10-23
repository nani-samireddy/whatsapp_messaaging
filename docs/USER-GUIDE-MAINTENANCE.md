# Maintaining the user guide

Users open **User guide** from any of the three workspaces or the app sidebar. Inbox and Automation have a User guide button; relevant forms have **Help → User guide**. Each workflow has a bookmarkable `/desk/whatsapp-guide/<workflow>` route, role label, plain-language purpose description, steps, screenshot, expected result and related guides. Search matches the workflow text; category filtering narrows the results. Screenshots can be enlarged in a separate tab. Additional screenshots are expandable so the steps remain easy to reach.

The source of truth is `whatsapp_messaging/public/docs/user-guide.json`. UI rendering is in `public/js/user_guide.js` and the `whatsapp-guide` standard Page. Update instructions and captions when controls change, then run `python3 scripts/export_user_guides.py` to regenerate the repository's [Markdown guide](user-guide/README.md). Run the normal app build and migration to update installed sites.

## Updating screenshots

Screenshots in `public/docs/screenshots/` are real application captures from the isolated `whatsapp-test.localhost` site, following Riverbend Hospital’s fictional patient-services team, reserved training phone numbers and dummy credentials. These public assets must never contain real conversations, patient/customer records, credentials, login links or private files.

1. Start the [isolated integration harness](../tests/integration/README.md) with its internal-only Docker network. Do not use an existing development or production site's database.
2. Run `tests/integration/seed_guide.py` inside its test container after the integration suite. The script refuses any other site/database host, creates only fictional examples and mocks provider requests. It leaves automation off; no worker or scheduler is started. Its fixture route identifiers are written to `/testbench/guide-fixtures.json` in the disposable volume.
3. Serve that test site using the bench environment with the app's built assets available. If browser access requires a local bridge, keep it bound to loopback and preserve the test network's isolation. Do not expose a public tunnel or connect Meta.
4. Capture the named workflow screens through the browser. Confirm fields have rendered and relevant controls are visible. Keep tokens and secrets masked. Capture additional views for long forms rather than omitting the action referenced by the instructions.
5. Replace the matching image files, update the manifest's capture date and captions, regenerate Markdown, and check every image in the guide. Validate search, deep links, image enlargement, related links and a narrow phone viewport.
6. Remove only the disposable test project's containers, network, volumes and any temporary loopback bridge. Do not remove the actual development stack.

The guide content and example images are static public assets. Access to actual actions, records and credentials continues to be enforced by the existing roles and server permissions. The guide does not enable any integration switch or send messages.

Keep each workflow’s purpose description neutral: explain what the app does and why the workflow is useful. Use the hospital scenario in walkthroughs and screenshots. Description typography follows the app’s font stack, text size and color tokens.
