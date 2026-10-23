# Existing WhatsApp roles

The app reuses **Whatsapp Admin** and **Whatsapp Editor** from its existing role fixtures. Users keep their ordinary Frappe login. There is no additional user store, separate login or new role to assign.

Authorized users can use the configured sender accounts through their role permissions. No per-phone membership setup is required for this version. Standard Frappe user permissions still apply, including permission to read the business record used by a template. Assigning a WhatsApp role does not grant Patient, Patient Visit or other business-record access.

| Capability | Whatsapp Editor | Whatsapp Admin | System Manager |
|---|---|---|---|
| View conversation/message history | Yes | Yes | Yes |
| Send a single message or reply through the messaging service | Yes | Yes | Yes |
| Start a bulk campaign | No | Yes | Yes |
| Activate event rules and schedules | Yes | Yes | Yes |
| Claim/release and change status | Own or unassigned conversations | All conversations | All conversations |
| Assign another agent | No | Yes | Yes |
| Record consent or suppression | No | Yes | Yes |
| Read sender labels and phone IDs | Yes | Yes | Yes |
| Read/change sender tokens or edit sender configuration | No | No | Yes |
| Edit/delete canonical message history through generic document APIs | No | No | No |
| Create/edit reusable message content and campaign configuration | Yes | Yes | Yes |
| Select approved fields and enter fictional variable examples | Yes | Yes | Yes |
| Approve shared source/settings fields | No | No | Yes |
| Sync/import Meta templates and submit/check Meta review | No | Yes | Yes |
| Static recipients | Read | Manage | Manage |
| Integration settings | No access | Read-only | Manage |
| Enable outbound requests | No | No | Yes |

The sender token remains an encrypted Password field at permission level 1. App roles have only level-0 sender read/select permissions. The message send service uses the credential on the server after authorization; it does not return it to agents.

Messaging and Templates & Automation are visible to the three existing roles. Administration is visible to Whatsapp Admin/System Manager; its credentials and integration switches remain System Manager-only. The inbox thread/reply screen is implemented at `/app/whatsapp-inbox`. Assignment affects workflow actions, not shared visibility or send access. Source-driven sends and file/record links require the corresponding permissions.

`whatsapp_messaging.send_security.get_messaging_access` returns capabilities for the current Frappe session. This is for UI presentation; the send routes also enforce roles, source/template access, filters and policy on the backend. Editors can configure campaigns; bulk preview/start requires Whatsapp Admin/System Manager. Both app roles can activate event automations and schedules, executing with their own source permissions. Only System Manager can approve the shared source/settings fields available to every template. Selecting an already approved field does not expand the user's access to its source record. Operational queue/history records are changed through dedicated service actions, with immutable content and append-only attempts/activity.

The role definitions and DocType permissions do not assign roles to existing users automatically. An authorized administrator can assign the existing roles through Frappe's normal User form.
