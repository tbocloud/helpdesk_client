// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// Get help from a form (TBO Copilot Phase 14). Every form has a Get help button: it opens the support
// chat about that record. An error message (Frappe's red message dialog) has Get help with this error:
// the record and the error go to TBO Support at once, so it does not ask for them again. A record with
// one of the user's open tickets about it shows a Support strip linking to that ticket's chat.

frappe.provide("genie");

genie.FORM_ACTIONS = ["Save", "Submit", "Cancel", "Update", "Amend"];
genie.NO_HELP_BUTTON = ["Support Ticket", "Support Conversation", "HDS Support Settings"];

genie.chat_on = function () {
	return !!(frappe.boot.genie_chat_enabled && !frappe.boot.genie_hub_user);
};

// Open the panel on a new chat about a record ({doctype, name, page_route}), or about an error on it
// (also {error, action}).
genie.ask_about = function (ctx) {
	if (genie.refuse_hub_user()) return;
	new genie.SupportChat({ about: ctx });
};

// --- the form's button and Support strip ----------------------------------------------------------

genie.add_help_button = function (frm) {
	if (!genie.chat_on() || !frm || !frm.meta || frm.meta.istable) return;
	if (genie.NO_HELP_BUTTON.includes(frm.doctype)) return;
	frm.add_custom_button(__("Get help"), () =>
		genie.ask_about({
			doctype: frm.doctype,
			name: frm.is_new() ? "" : String(frm.docname),
			page_route: genie.capture_context().page_route,
		})
	);
	genie.support_strip(frm);
};

genie.strip_cache = {};

genie.support_strip = async function (frm) {
	const wrapper = frm.layout && frm.layout.wrapper;
	if (!wrapper) return;
	wrapper.parent().children(".genie-support-strip").remove();
	if (frm.is_new()) return;
	const doctype = frm.doctype;
	const name = String(frm.docname);
	const key = `${doctype}/${name}`;
	const cached = genie.strip_cache[key];
	let rows = cached && Date.now() - cached.at < 60000 ? cached.rows : null;
	if (!rows) {
		rows = await frappe
			.xcall("helpdesk_client.inbox.for_record", { doctype, docname: name })
			.catch(() => []);
		genie.strip_cache[key] = { rows, at: Date.now() };
	}
	// the user may have moved to another record meanwhile
	if (!rows.length || frm.doctype !== doctype || String(frm.docname) !== name) return;
	wrapper.parent().children(".genie-support-strip").remove();
	const strip = document.createElement("div");
	strip.className = "genie-support-strip";
	strip.setAttribute("role", "region");
	strip.setAttribute("aria-label", __("Support tickets about this record"));
	const label = document.createElement("b");
	label.textContent = __("Support");
	strip.appendChild(label);
	rows.forEach((row) => {
		const b = document.createElement("button");
		b.type = "button";
		b.append(genie.dot(row.dot), document.createTextNode(`${row.name} · ${row.line}`));
		b.title = __("Open {0}'s chat", [row.name]);
		b.onclick = () => new genie.SupportChat({ tab: "tickets", ticket: row.name });
		strip.appendChild(b);
	});
	wrapper.before(strip);
};

// --- the error message's button -------------------------------------------------------------------

// What the user pressed on a form, so "Submit failed on …" can say so.
genie.watch_form_actions = function () {
	$(document).ajaxSend((e, xhr, settings) => {
		const url = String((settings && settings.url) || "");
		if (!/frappe\.desk\.form\.save\.(savedocs|cancel)/.test(url)) return;
		let action = url.includes(".cancel") ? "Cancel" : "";
		if (!action) {
			try {
				action = new URLSearchParams(String(settings.data || "")).get("action") || "";
			} catch (err) {
				action = "";
			}
		}
		genie.last_form_action = {
			action: genie.FORM_ACTIONS.includes(action) ? action : "",
			at: Date.now(),
			route: genie.capture_context().page_route,
		};
	});
};

genie.offer_error_help = function () {
	const d = frappe.msg_dialog;
	if (!d || !d.$wrapper) return;
	d.$wrapper.find(".genie-error-help, .genie-error-note").remove();
	const red = d.indicator && d.indicator.hasClass && d.indicator.hasClass("red");
	// the dialog is still fading in here: being red is enough
	if (!red || !genie.chat_on()) return;
	const error = (d.msg_area ? d.msg_area.text() : "").replace(/\s+/g, " ").trim().slice(0, 500);
	if (!error) return;
	const ctx = genie.capture_context();
	const last = genie.last_form_action;
	const action =
		last && Date.now() - last.at < 30000 && last.route === ctx.page_route ? last.action : "";
	d.add_custom_action(
		__("Get help with this error"),
		() => {
			d.hide();
			genie.ask_about({
				doctype: ctx.ref_doctype,
				name: ctx.ref_docname,
				page_route: ctx.page_route,
				error,
				action,
			});
		},
		"genie-error-help btn-primary"
	);
	const note = document.createElement("div");
	note.className = "genie-error-note";
	note.textContent = ctx.ref_doctype
		? __("TBO Support gets the record's name and this message, not the record's contents.")
		: __("TBO Support gets this message and the page you are on.");
	d.body.appendChild(note);
	d.$wrapper.one("hidden.bs.modal", () =>
		d.$wrapper.find(".genie-error-help, .genie-error-note").remove()
	);
};

genie.watch_errors = function () {
	if (genie.watching_errors) return;
	genie.watching_errors = true;
	const original = frappe.msgprint;
	frappe.msgprint = function (...args) {
		const shown = original.apply(this, args);
		setTimeout(() => {
			try {
				genie.offer_error_help();
			} catch (e) {
				// the error message itself must never break
			}
		}, 0);
		return shown;
	};
	genie.watch_form_actions();
};

$(document).on("app_ready", function () {
	if (!genie.chat_on()) return;
	genie.watch_errors();
	// a ticket changed: the strips show it next time
	genie.support_inbox.on(() => (genie.strip_cache = {}));
});

$(document).on("form-refresh", function (e, frm) {
	try {
		genie.add_help_button(frm);
	} catch (err) {
		// a form must never break because of the Support button
	}
});
