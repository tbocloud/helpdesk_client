// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.ui.form.on("Content Approval", {
	refresh(frm) {
		if (frm.doc.status !== "Pending" || frm.is_new()) return;

		frm.add_custom_button(__("Approve"), () => {
			frm.set_value("status", "Approved");
			frm.save().then(() => frappe.show_alert({ message: __("Approved"), indicator: "green" }));
		}).addClass("btn-primary");

		frm.add_custom_button(__("Request changes"), () => {
			frappe.prompt(
				{
					fieldname: "comment",
					fieldtype: "Small Text",
					label: __("What should change?"),
					reqd: 1,
				},
				({ comment }) => {
					frm.set_value("client_comment", comment);
					frm.set_value("status", "Changes Requested");
					frm.save().then(() =>
						frappe.show_alert({ message: __("Sent back to the team"), indicator: "orange" })
					);
				},
				__("Request changes"),
				__("Send")
			);
		});
	},
});
