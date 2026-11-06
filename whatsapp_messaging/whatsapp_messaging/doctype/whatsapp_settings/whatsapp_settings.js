// Copyright (c) 2024, nani-samireddy and contributors
// For license information, please see license.txt

frappe.ui.form.on("WhatsApp Settings", {
	refresh(frm) {
		if (!frappe.user.has_role("System Manager")) return;
		frm.add_custom_button(__("Check setup"), async () => {
			const { message: report } = await frappe.call({
				method: "whatsapp_messaging.messaging.readiness.check",
				type: "GET",
				freeze: true,
				freeze_message: __("Checking saved settings and worker status…"),
			});
			const escape = frappe.utils.escape_html;
			const rows = report.checks.map((row) => `<tr>
				<td>${escape(row.label)}</td>
				<td>${row.status === "pass" ? __("Passed") : __("Action needed")}</td>
				<td>${escape(row.detail)}</td></tr>`).join("");
			const warnings = report.warnings.map((row) =>
				`<li>${escape(String(row.count))}: ${escape(row.detail)}</li>`).join("");
			const next = report.external_verification_required.map((text) =>
				`<li>${escape(text)}</li>`).join("");
			frappe.msgprint({
				title: __("WhatsApp setup check"),
				wide: true,
				message: `<p>${__("This checks saved configuration. No messages are sent and no settings are changed.")}</p>
					<div class="table-responsive"><table class="table table-bordered">
					<thead><tr><th>${__("Check")}</th><th>${__("Result")}</th><th>${__("Details")}</th></tr></thead>
					<tbody>${rows}</tbody></table></div>
					${warnings ? `<p><strong>${__("Needs review")}</strong></p><ul>${warnings}</ul>` : ""}
					<p><strong>${__("Still verify on this deployment")}</strong></p><ul>${next}</ul>`,
			});
		});
	},
});
