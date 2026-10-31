// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// The Support panel on its own page (TBO Copilot Phase 13): New chat, Action needed, Tickets and
// Chats down the left, the chat on the right. /app/support-chat/SUP-2026-00011 opens that ticket's
// chat, /app/support-chat/SUPCONV-2026-00004 that chat.

frappe.pages["support-chat"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Support"),
		single_column: true,
	});
	genie.support_page = new genie.SupportPage(page);
};

frappe.pages["support-chat"].on_page_show = function () {
	if (genie.support_page) genie.support_page.follow_route();
};

// the floating Support button and panel would cover this page's own Send button
genie.on_support_page = function () {
	document.body.classList.toggle(
		"genie-on-support-page",
		frappe.get_route()[0] === "support-chat"
	);
};

genie.SupportPage = class SupportPage {
	constructor(page) {
		this.page = page;
		this.current = undefined;
		genie.support_css();
		page.set_secondary_action(__("All ticket records"), () =>
			frappe.set_route("List", "Support Ticket")
		);
		const box = document.createElement("div");
		box.className = "genie-sc-page";
		box.innerHTML = `
			<aside class="genie-sc-rail" aria-label="${__("Your tickets and chats")}">
				<button type="button" class="btn btn-default btn-sm btn-block genie-sc-new">+ ${__(
					"New chat"
				)}</button>
				<div class="genie-sc-rail-list"></div>
			</aside>
			<section class="genie-sc-main"></section>`;
		page.main.get(0).appendChild(box);
		this.rail = box.querySelector(".genie-sc-rail-list");
		box.querySelector(".genie-sc-new").onclick = () => this.new_chat();
		const go = (name) => this.go(name);
		this.view = new genie.SupportChatView(box.querySelector(".genie-sc-main"), {
			show_head: true,
			on_open_ticket: go,
			on_ticket: go,
			on_chat: (name) => {
				this.current = name; // already shown: only the address follows
				frappe.set_route("support-chat", name);
			},
			on_new_chat: () => this.new_chat(),
		});
		genie.support_inbox.listen();
		genie.support_inbox.on((data) => this.render_rail(data));
		frappe.router.on("change", () => {
			genie.on_support_page();
			if (frappe.get_route()[0] === "support-chat") this.follow_route();
		});
		genie.support_inbox
			.load()
			.catch(() => null)
			.then(() => this.follow_route());
	}

	go(name) {
		frappe.set_route(...["support-chat", name].filter(Boolean));
	}

	new_chat() {
		this.current = null;
		if (frappe.get_route()[1]) frappe.set_route("support-chat");
		this.render_rail(genie.support_inbox.data);
		this.view.start_new();
	}

	follow_route() {
		genie.on_support_page();
		if (frappe.boot.genie_hub_user) {
			this.view.waiting();
			this.view.typing(false);
			this.view.body.innerHTML = `<div class="genie-sc-empty">${__(
				"You're signed in as TBO Support. This page is for the customer's own users."
			)}</div>`;
			return;
		}
		const name = frappe.get_route()[1] || null;
		if (name === this.current) return;
		this.current = name;
		this.render_rail(genie.support_inbox.data);
		if (!name) return this.welcome();
		if (name.startsWith("SUPCONV-")) this.view.open_chat(name);
		else this.view.open_ticket(name);
	}

	welcome() {
		const data = genie.support_inbox.data;
		this.view.waiting();
		this.view.typing(false);
		const div = document.createElement("div");
		div.className = "genie-sc-empty";
		div.textContent = data.actions.length
			? __("{0} of your tickets wait for you: pick one on the left.", [data.actions.length])
			: __("Pick a ticket or a chat on the left, or start a new chat.");
		this.view.body.appendChild(div);
	}

	render_rail(data) {
		this.rail.innerHTML = "";
		const section = (title, rows, opts = {}) => {
			if (!rows.length && !opts.always) return;
			const h = document.createElement("div");
			h.className = "genie-sc-rail-heading";
			h.textContent = title;
			this.rail.appendChild(h);
			if (!rows.length) {
				const none = document.createElement("div");
				none.className = "text-muted";
				none.style.cssText = "font-size:12px;padding:2px 10px";
				none.textContent = opts.empty;
				this.rail.appendChild(none);
			}
			rows.forEach((row) =>
				this.rail.appendChild(
					genie.inbox_item(row, () => this.go(row.name), {
						need: opts.need,
						active: row.name === this.current,
					})
				)
			);
		};
		section(`${__("Action needed")} (${data.actions.length})`, data.actions, {
			need: true,
			always: true,
			empty: __("Nothing needs you right now."),
		});
		section(__("Tickets"), data.tickets, { always: true, empty: __("No tickets yet.") });
		section(__("Chats"), data.chats);
	}
};
