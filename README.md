# WhatsApp Messaging

A Frappe app for WhatsApp conversations, reusable message content, media and campaigns. Users sign in with their existing Frappe account and use the existing Whatsapp Editor, Whatsapp Admin and System Manager roles.

## Workflows

- **Messaging:** shared Inbox, replies, approved-template messages, private images/PDFs, assignment, business-record links and delivery history.
- **Templates & Automation:** reusable content with shared field pickers, text headers/footers, live preview, selective Meta import, explicit submission/review, campaigns, document events and schedules.
- **Administration:** sender credentials, integration switches, consent/suppression, Outbox, send attempts and signed webhook diagnostics.

Templates define the message. Campaigns define its audience and sending rules. Saving content or uploading media does not send a message. Outbox acceptance and provider delivery receipts are shown separately.

Open **User guide** from a workspace or **Help → User guide** on supported forms for purpose, steps and hospital screenshots. The training scenario uses fictional Riverbend Hospital records.

## Local setup

The current checkout is developed and tested against Frappe 16.52.0. With this app already checked out in the bench's `apps` directory, install it on a new site:

```sh
bench --site YOUR_SITE install-app whatsapp_messaging
bench --site YOUR_SITE migrate
bench build --app whatsapp_messaging
```

For an existing installation, migrate and rebuild assets. Open `/desk/whatsapp-messaging` and assign the appropriate existing app role through Frappe's User form.

A System Manager configures the sender, WABA and encrypted access token. Outbound requests, inbound events and automation have independent switches and default off. Queued work requires the appropriate workers and scheduler; media cloud uploads use the dedicated `whatsapp_media` queue. See [operation and workspaces](docs/WORKSPACES-AND-INBOX.md) and [media setup](docs/MEDIA-LIBRARY-REVIEW.md).

## Documentation

- [App completion status](docs/APP-COMPLETION.md)
- [User guide](docs/user-guide/README.md)
- [Roles and permissions](docs/ROLE-PERMISSIONS.md)
- [Templates, campaigns and Meta review](docs/TEMPLATES-AND-CAMPAIGNS.md)
- [Implementation and migration history](docs/IMPLEMENTATION-PROGRESS.md)

## Verification

```sh
python3 -m unittest discover -s tests -v
```

The [isolated integration harness](tests/integration/README.md) verifies a fresh install, migrations, database/HTTP permissions, worker execution, messaging, webhooks, templates, media and automation using fictional fixtures and mocked provider transport. It uses its own internal Docker network, database and Redis.

Live Meta acceptance and public webhook delivery are tracked separately in the completion status; passing local tests does not establish provider delivery. The home server is outside the current development work.

## Contributing

Formatting and lint hooks are configured in `.pre-commit-config.yaml`. Install `pre-commit` and run `pre-commit install` before contributing.

## License

MIT.
