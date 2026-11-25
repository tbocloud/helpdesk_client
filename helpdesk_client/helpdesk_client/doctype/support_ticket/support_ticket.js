// Copyright (c) 2026, Wahni IT Solutions Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Support Ticket", {
	refresh(frm) {
		genie_ticket.render_stage(frm);
		genie_ticket.render_updates(frm);
		genie_ticket.render_recent_errors(frm);
		genie_ticket.add_buttons(frm);
		if (!frm.is_new() && frappe.boot.genie_chat_enabled) {
			// every ticket is a chat (TBO Copilot Phase 13)
			frm.add_custom_button(__("Open its chat"), () =>
				frappe.set_route("support-chat", frm.doc.name)
			);
		}
		if (frm.doc.ticket_id) {
			frm.dashboard.add_indicator(
				__("TBO Support ticket #{0}", [frm.doc.ticket_id]),
				"blue"
			);
		}
	},
});

const genie_ticket = {
	STAGE_COLORS: {
		Received: "gray",
		"Working on it": "blue",
		"Fix scheduled": "orange",
		Resolved: "green",
		"With our team": "purple",
		"Waiting for you": "yellow",
	},

	method(name) {
		return `helpdesk_client.helpdesk_client.doctype.support_ticket.support_ticket.${name}`;
	},

	// The raiser's own recent errors. Recent Errors itself is for System Managers only: a follower
	// reads the rest of the ticket, and the errors may be about another part of the business.
	render_recent_errors(frm) {
		const field = frm.get_field("recent_errors_html");
		if (!field) return;
		const raw = frm.doc.__onload && frm.doc.__onload.recent_errors;
		let errors = [];
		try {
			errors = raw ? JSON.parse(raw) : [];
		} catch (e) {
			errors = [{ error: raw }];
		}
		const shown = Array.isArray(errors) && errors.length;
		frm.toggle_display("recent_errors_html", Boolean(shown));
		if (!shown) return;
		const esc = frappe.utils.escape_html;
		const rows = errors
			.map((row) => {
				const where = [row.at, row.method, row.reference].filter(Boolean).join(" · ");
				return `<div class="mb-2"><div class="text-muted small">${esc(where)}</div>
					<pre class="small mb-0">${esc(row.error || "")}</pre></div>`;
			})
			.join("");
		field.$wrapper.html(
			`<label class="control-label">${esc(__("Your Recent Errors"))}</label>${rows}`
		);
	},

	// The stage banner: where TBO Support is, in the customer's words.
	render_stage(frm) {
		const esc = frappe.utils.escape_html;
		const closing =
			frm.doc.close_requested && frm.doc.status !== "Closed"
				? __("Close requested — awaiting confirmation from support.")
				: "";
		if (frm.doc.stage) {
			frm.page.set_indicator(__(frm.doc.stage), this.STAGE_COLORS[frm.doc.stage] || "gray");
			const message = frm.doc.stage_message ? ` — ${esc(frm.doc.stage_message)}` : "";
			// asked to close: said under the stage, which stays
			const asked = closing ? `<div>${esc(closing)}</div>` : "";
			frm.dashboard.set_headline(`<b>${esc(__(frm.doc.stage))}</b>${message}${asked}`);
		} else if (closing) {
			frm.dashboard.set_headline(closing);
		} else if (frm.doc.status === "Pending") {
			frm.dashboard.set_headline(__("Submitted — support will pick this up shortly."));
		}
		// only an answer to the latest Resolved still stands: an older one was about an earlier fix
		if (!this.state(frm).answered) return;
		if (frm.doc.customer_confirmation === "Confirmed") {
			frm.dashboard.add_comment(
				__("You confirmed this is fixed. Thank you."),
				"green",
				true
			);
		} else if (frm.doc.customer_confirmation === "Reopened") {
			frm.dashboard.add_comment(
				__("You reopened this ticket; a person at TBO Support is taking it over."),
				"orange",
				true
			);
		}
	},

	// Every message TBO Support posted, newest first.
	render_updates(frm) {
		const field = frm.fields_dict.updates_html;
		if (!field) return;
		const esc = frappe.utils.escape_html;
		const rows = (frm.doc.updates || [])
			.slice()
			.sort((a, b) => (b.posted_at || "").localeCompare(a.posted_at || ""));
		if (!rows.length) {
			field.$wrapper.html(`<div class="text-muted">${__("No updates yet.")}</div>`);
			return;
		}
		field.$wrapper.html(
			rows
				.map(
					(row) => `
			<div style="padding: 6px 0; border-bottom: 1px solid var(--border-color);">
				<div>
					<b>${esc(__(row.stage || row.kind || ""))}</b>
					<span class="text-muted small">
						${esc(row.author_name || "")}${
						row.posted_at ? " · " + esc(frappe.datetime.prettyDate(row.posted_at)) : ""
					}
					</span>
				</div>
				<div>${esc(row.message || "")}</div>
			</div>`
				)
				.join("")
		);
	},

	// The ticket's state as the chat sees it (Phase 23): the server works it out on load.
	state(frm) {
		return (frm.doc.__onload && frm.doc.__onload.genie) || {};
	},

	add_buttons(frm) {
		// "Is it fixed?" after every Resolved, not once per ticket: a second fix asks again
		if (this.state(frm).confirm) {
			frm.add_custom_button(__("Confirm, it's fixed"), () =>
				this.call(
					frm,
					"confirm_resolution",
					{},
					__("Thank you. The ticket will be closed.")
				)
			).addClass("btn-primary");
			frm.add_custom_button(__("Still broken, reopen"), () =>
				frappe.prompt(
					{
						fieldname: "note",
						fieldtype: "Small Text",
						label: __("What is still wrong?"),
						reqd: 1,
					},
					(values) =>
						this.call(
							frm,
							"reopen",
							{ note: values.note },
							__("Reopened. A person will take it over.")
						),
					__("Reopen the ticket")
				)
			);
			return;
		}
		if (!["Closed", "Resolved"].includes(frm.doc.status) && !frm.doc.close_requested) {
			frm.add_custom_button(__("Close Ticket"), () =>
				this.call(
					frm,
					"request_close",
					{},
					__("Close requested — support will confirm shortly.")
				)
			);
		}
	},

	async call(frm, method, args, message) {
		await frappe.call({
			method: this.method(method),
			type: "POST",
			args: { ticket: frm.doc.name, ...args },
		});
		frappe.show_alert({ indicator: "green", message });
		frm.reload_doc();
	},
};
