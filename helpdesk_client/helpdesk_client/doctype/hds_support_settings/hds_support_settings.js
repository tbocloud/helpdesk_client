// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.ui.form.on("Helpdesk Support Settings", {
	refresh(frm) {
		if (frm.doc.client_id) {
			frm.dashboard.add_indicator(
				__("Registered with Hub: {0}", [frm.doc.client_id]),
				"green"
			);
		} else {
			frm.dashboard.add_indicator(__("Not registered"), "orange");
		}

		frm.add_custom_button(__("Open support@quarkcs.com User"), function () {
			frappe.set_route("Form", "User", "support@quarkcs.com");
		});
	},
});
