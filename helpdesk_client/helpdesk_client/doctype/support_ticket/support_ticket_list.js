// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.listview_settings["Support Ticket"] = {
	add_fields: ["ticket_id", "stage"],
	formatters: {
		// the hub's number is what customers quote when they call
		ticket_id(value) {
			return value
				? `<span class="text-muted">#</span>${frappe.utils.escape_html(value)}`
				: "";
		},
	},
	get_indicator(doc) {
		const colors = {
			Received: "gray",
			"Working on it": "blue",
			"Fix scheduled": "orange",
			Resolved: "green",
			"With our team": "purple",
			"Waiting for you": "yellow",
		};
		if (doc.stage) {
			return [__(doc.stage), colors[doc.stage] || "gray", "stage,=," + doc.stage];
		}
		const status_colors = { Pending: "gray", Open: "blue", Replied: "orange", Paused: "yellow", Resolved: "green", Closed: "green" };
		return [__(doc.status), status_colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
