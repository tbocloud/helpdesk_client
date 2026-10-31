// Copyright (c) 2026, Quark Cyber Systems FZC and Contributors
// Adds a persistent Support button to the desk. Only shows when ticket raising is enabled in
// HDS Support Settings (frappe.boot.genie_support_enabled). With the chat on (TBO Copilot), it opens
// the Support panel, and a red "Actions needed" button above it shows while tickets wait for the
// user (Phase 13). Without the chat, it offers the form and the ticket list.

frappe.provide("genie");

$(document).on("app_ready", function () {
	genie.setup_ticket_launcher();
});

// TBO Support signed in with Login to site: a ticket would be raised as TBO, not the customer
genie.refuse_hub_user = function () {
	if (!frappe.boot.genie_hub_user) return false;
	frappe.msgprint({
		title: __("Signed in as TBO Support"),
		message: __(
			"You're signed in as TBO Support. The Support button is for the customer's own users: sign in as one of them to raise a ticket."
		),
		indicator: "orange",
	});
	return true;
};

genie.setup_ticket_launcher = function () {
	if (!frappe.boot.genie_support_enabled) return;
	if (document.getElementById("genie-support-fab")) return;

	const fab = document.createElement("button");
	fab.id = "genie-support-fab";
	fab.type = "button";
	fab.className = "btn btn-primary btn-sm";
	fab.title = __("Support");
	fab.setAttribute("aria-label", __("Support"));
	fab.innerHTML = `<svg class="icon icon-sm" style="vertical-align: middle;"><use href="#icon-message"></use></svg>`;
	Object.assign(fab.style, {
		position: "fixed",
		right: "24px",
		bottom: "24px",
		zIndex: "1030",
		borderRadius: "50%",
		width: "44px",
		height: "44px",
		boxShadow: "0 2px 10px rgba(0, 0, 0, 0.25)",
	});
	document.body.appendChild(fab);

	if (frappe.boot.genie_chat_enabled) {
		genie.setup_actions_button();
		fab.addEventListener("click", () => {
			if (genie.refuse_hub_user()) return;
			const panel = genie.support_chat;
			if (
				panel &&
				panel.panel.style.display !== "none" &&
				document.body.contains(panel.panel)
			) {
				panel.hide();
				return;
			}
			new genie.SupportChat();
		});
		return;
	}
	genie.setup_ticket_menu(fab);
};

// The red button: how many tickets wait for the user; it opens the panel on Action needed.
genie.setup_actions_button = function () {
	if (frappe.boot.genie_hub_user) return;
	const b = document.createElement("button");
	b.id = "genie-actions-btn";
	b.type = "button";
	b.className = "btn btn-danger btn-sm";
	Object.assign(b.style, {
		position: "fixed",
		right: "24px",
		bottom: "76px",
		zIndex: "1030",
		borderRadius: "20px",
		padding: "6px 14px",
		boxShadow: "0 2px 10px rgba(0, 0, 0, 0.2)",
	});
	b.addEventListener("click", () => new genie.SupportChat({ tab: "actions" }));
	document.body.appendChild(b);
	const show = (n) => {
		b.textContent = `● ${__("Actions needed")} · ${n}`;
		b.style.display = n ? "block" : "none";
		b.setAttribute("aria-label", __("{0} tickets wait for you", [n]));
	};
	show(frappe.boot.genie_actions_needed || 0);
	genie.support_inbox.on((data) => show(data.actions.length));
	genie.support_inbox.listen();
};

// Without the chat: the form, and the list of the user's tickets.
genie.setup_ticket_menu = function (fab) {
	const mk = (id, label, bottom, onclick) => {
		const b = document.createElement("button");
		b.id = id;
		b.type = "button";
		b.className = "btn btn-default btn-sm";
		b.textContent = label;
		Object.assign(b.style, {
			position: "fixed",
			right: "24px",
			bottom: bottom,
			zIndex: "1030",
			borderRadius: "20px",
			padding: "6px 14px",
			boxShadow: "0 2px 10px rgba(0, 0, 0, 0.2)",
			display: "none",
			transition: "opacity 0.15s",
		});
		b.addEventListener("click", () => {
			toggle(false);
			onclick();
		});
		document.body.appendChild(b);
		return b;
	};

	const actions = [
		mk("genie-raise-ticket-btn", __("Raise a Ticket"), "76px", () => {
			if (genie.refuse_hub_user()) return;
			return new genie.SupportTicket();
		}),
		mk("genie-my-tickets-btn", __("My Tickets"), "116px", () =>
			frappe.set_route("List", "Support Ticket")
		),
	];

	let open = false;
	const toggle = (state) => {
		open = state === undefined ? !open : state;
		actions.forEach((a) => (a.style.display = open ? "block" : "none"));
		fab.style.transform = open ? "rotate(90deg)" : "";
	};
	fab.addEventListener("click", () => toggle());
};
