// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.ui.form.on("HDS Support Settings", {
	refresh(frm) {
		if (frm.doc.client_id) {
			frm.dashboard.add_indicator(
				__("Registered with Hub: {0}", [frm.doc.client_id]),
				"green"
			);
		} else {
			frm.dashboard.add_indicator(__("Not registered"), "orange");
		}

		if (!frm.doc.client_id) {
			frm.add_custom_button(__("Connect to TBO Support"), () =>
				connect_to_hub(frm)
			).addClass("btn-primary");
		}

		const supportUser = frm.doc.support_user || "support@teambackoffice.com";
		frm.add_custom_button(__("Open {0} User", [supportUser]), function () {
			frappe.set_route("Form", "User", supportUser);
		});
	},
});

function connect_to_hub(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Connect to TBO Support"),
		fields: [
			{
				fieldname: "code",
				fieldtype: "Data",
				label: __("Connection code"),
				description: __(
					"Ask TBO Support for the code (e.g. K7PQ-2MXD-9R). It works once."
				),
				reqd: 1,
			},
			{
				fieldname: "hub_url",
				fieldtype: "Data",
				label: __("TBO Support URL"),
				default: frm.doc.qcs_hub_url || "https://teams.teambackoffice.com",
				reqd: 1,
			},
		],
		primary_action_label: __("Connect"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "helpdesk_client.api.connect_to_hub",
				args: values,
				freeze: true,
				freeze_message: __("Connecting to TBO Support..."),
				callback() {
					frappe.show_alert({
						message: __("Connected to TBO Support"),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}
