// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.listview_settings["Support Ticket"] = {
	add_fields: ["ticket_id"],
	formatters: {
		// the hub's number is what customers quote when they call
		ticket_id(value) {
			return value
				? `<span class="text-muted">#</span>${frappe.utils.escape_html(value)}`
				: "";
		},
	},
};
