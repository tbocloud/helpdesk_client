// Copyright (c) 2026, Wahni IT Solutions Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Support Ticket", {
	refresh: function (frm) {
		if (!["Closed", "Resolved"].includes(frm.doc.status) && !frm.doc.close_requested) {
			frm.add_custom_button(__("Close Ticket"), async () => {
				await frappe.call({
					method: "helpdesk_client.helpdesk_client.doctype.support_ticket.support_ticket.request_close",
					args: { ticket: frm.doc.name },
				});
				frappe.show_alert({ indicator: "green", message: __("Close requested — support will confirm shortly.") });
				frm.reload_doc();
			});
		}
		if (frm.doc.close_requested && frm.doc.status !== "Closed") {
			frm.dashboard.set_headline(__("Close requested — awaiting confirmation from support."));
		}
		// Status is pushed here by the Hub over MCP — there is nothing for
		// the client to fetch, so no "Refresh Status" button.
		if (frm.doc.status === "Pending") {
			frm.dashboard.set_headline(
				__("Submitted — support will pick this up shortly.")
			);
		}
	},
});
