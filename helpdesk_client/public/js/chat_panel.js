// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// The Support panel (TBO Copilot Phase 5, tabs in Phase 13): the Support button opens it.
// Tickets: a dropdown of the user's tickets, each with its own chat. New chat: the chats that did
// not become tickets. Action needed: the red tickets, each with what is needed. This site relays
// each message (helpdesk_client.chat); what TBO Support starts later arrives live over realtime.

frappe.provide("genie");

genie.SupportChat = class SupportChat {
	constructor(opts = {}) {
		if (genie.support_chat && document.body.contains(genie.support_chat.panel)) {
			genie.support_chat.show(opts.tab, opts.ticket);
			return genie.support_chat;
		}
		genie.support_chat = this;
		genie.support_css();
		this.tab = null;
		this.picked = { tickets: null, chats: null };
		this.build();
		genie.support_inbox.listen();
		genie.support_inbox.on(() => this.update());
		genie.support_inbox
			.load()
			.catch(() => null)
			.then(() => this.show(opts.tab, opts.ticket));
	}

	build() {
		const panel = document.createElement("div");
		panel.id = "genie-support-chat";
		panel.className = "genie-no-record";
		panel.setAttribute("role", "dialog");
		panel.setAttribute("aria-label", __("TBO Support"));
		Object.assign(panel.style, {
			position: "fixed",
			right: "24px",
			bottom: "90px",
			width: "420px",
			maxWidth: "calc(100vw - 32px)",
			height: "620px",
			maxHeight: "80vh",
			display: "flex",
			flexDirection: "column",
			background: "var(--card-bg, #fff)",
			color: "var(--text-color, #1f272e)",
			border: "1px solid var(--border-color, #e2e6e9)",
			borderRadius: "12px",
			boxShadow: "var(--shadow-lg, 0 8px 24px rgba(0,0,0,.18))",
			zIndex: 1031,
			overflow: "hidden",
		});
		panel.innerHTML = `
			<div style="display:flex;align-items:center;gap:8px;padding:10px 12px 0">
				<b style="flex:1">${__("TBO Support")}</b>
				<button type="button" class="btn btn-xs btn-default genie-sp-full">${__("Full page")}</button>
				<button type="button" class="btn btn-xs btn-default genie-sp-close" aria-label="${__(
					"Close"
				)}">×</button>
			</div>
			<div class="genie-sp-tabs" role="tablist" style="display:flex;gap:4px;padding:8px 12px 0;border-bottom:1px solid var(--border-color,#e2e6e9)">
				<button type="button" role="tab" data-tab="tickets">${__("Tickets")}</button>
				<button type="button" role="tab" data-tab="chats">${__("New chat")}</button>
				<button type="button" role="tab" data-tab="actions">${__(
					"Action needed"
				)} <span class="genie-sp-count"></span></button>
			</div>
			<div class="genie-sp-top" style="padding:8px 12px 0;display:flex;gap:6px;align-items:center"></div>
			<div class="genie-sp-list" style="flex:1;overflow-y:auto;padding:8px" hidden></div>
			<div class="genie-sp-view" style="flex:1;display:flex;flex-direction:column;min-height:0"></div>`;
		document.body.appendChild(panel);
		this.panel = panel;
		this.top = panel.querySelector(".genie-sp-top");
		this.list = panel.querySelector(".genie-sp-list");
		this.view_box = panel.querySelector(".genie-sp-view");
		this.view = new genie.SupportChatView(this.view_box, {
			on_open_ticket: (name) => this.show("tickets", name),
			on_ticket: (name) => this.show("tickets", name),
			on_chat: (name) => {
				this.picked.chats = name;
				this.render_top();
			},
			on_new_chat: () => this.new_chat(),
		});
		panel.querySelector(".genie-sp-close").onclick = () => this.hide();
		panel.querySelector(".genie-sp-full").onclick = () => {
			this.hide();
			const name =
				this.tab === "tickets"
					? this.picked.tickets
					: this.tab === "chats"
					? this.picked.chats
					: null;
			frappe.set_route(...["support-chat", name].filter(Boolean));
		};
		panel.querySelectorAll(".genie-sp-tabs button").forEach((b) => {
			b.className = "btn btn-xs btn-default";
			b.style.borderRadius = "8px 8px 0 0";
			b.onclick = () => this.show(b.dataset.tab);
		});
	}

	hide() {
		this.panel.style.display = "none";
		document.body.classList.remove("genie-support-open");
	}

	// tab: tickets / chats / actions; for tickets, which one to open
	show(tab, ticket) {
		const data = genie.support_inbox.data;
		this.panel.style.display = "flex";
		// the red button sits where the panel opens; the Action needed tab says the same
		document.body.classList.add("genie-support-open");
		tab = tab || this.tab || (data.tickets.length ? "tickets" : "chats");
		const changed = tab !== this.tab || (ticket && ticket !== this.picked.tickets);
		this.tab = tab;
		if (ticket) this.picked.tickets = ticket;
		this.panel.querySelectorAll(".genie-sp-tabs button").forEach((b) => {
			const on = b.dataset.tab === tab;
			b.setAttribute("aria-selected", on ? "true" : "false");
			b.classList.toggle("btn-primary", on);
			b.classList.toggle("btn-default", !on);
		});
		this.list.hidden = tab !== "actions";
		this.view_box.style.display = tab === "actions" ? "none" : "flex";
		this.render_top();
		this.render_actions();
		if (!changed) return;
		if (tab === "tickets") {
			this.picked.tickets = this.picked.tickets || (data.tickets[0] && data.tickets[0].name);
			if (this.picked.tickets) this.view.open_ticket(this.picked.tickets);
			else this.view.waiting();
		} else if (tab === "chats") {
			const current = this.picked.chats || (data.chats.find((c) => c.open) || {}).name;
			if (current) {
				this.picked.chats = current;
				this.view.open_chat(current);
			} else {
				this.new_chat();
			}
		}
	}

	new_chat() {
		if (this.tab !== "chats") {
			this.tab = "chats";
			this.show("chats");
		}
		this.picked.chats = null;
		this.render_top();
		this.view.start_new();
	}

	update() {
		this.render_top();
		this.render_actions();
	}

	render_top() {
		const data = genie.support_inbox.data;
		const count = this.panel.querySelector(".genie-sp-count");
		count.textContent = data.actions.length ? `(${data.actions.length})` : "";
		this.top.innerHTML = "";
		this.top.hidden = this.tab === "actions";
		if (this.tab === "tickets") {
			if (!data.tickets.length) {
				const none = document.createElement("span");
				none.className = "text-muted";
				none.style.fontSize = "12px";
				none.textContent = __(
					"No tickets yet. A chat becomes a ticket once TBO Support raises it."
				);
				this.top.appendChild(none);
				return;
			}
			this.top.appendChild(
				this.picker(
					__("Ticket"),
					data.tickets.map((t) => [
						t.name,
						`${genie.DOT_EMOJI[t.dot] || ""} ${t.name} · ${t.summary}`,
					]),
					this.picked.tickets,
					(name) => this.show("tickets", name)
				)
			);
		} else if (this.tab === "chats") {
			const chats = data.chats;
			if (chats.length) {
				this.top.appendChild(
					this.picker(
						__("Chat"),
						[
							...(this.picked.chats ? [] : [["", __("New chat")]]),
							...chats.map((c) => [
								c.name,
								`${c.summary} · ${frappe.datetime.prettyDate(c.last_activity)}`,
							]),
						],
						this.picked.chats || "",
						(name) => {
							if (!name) return;
							this.picked.chats = name;
							this.view.open_chat(name);
						}
					)
				);
			}
			const fresh = document.createElement("button");
			fresh.type = "button";
			fresh.className = "btn btn-xs btn-default";
			fresh.style.whiteSpace = "nowrap";
			fresh.textContent = "+ " + __("New chat");
			fresh.onclick = () => this.new_chat();
			this.top.appendChild(fresh);
		}
	}

	picker(label, options, value, onchange) {
		const select = document.createElement("select");
		select.className = "form-control input-xs";
		select.style.flex = "1";
		select.setAttribute("aria-label", label);
		options.forEach(([name, text]) => {
			const o = document.createElement("option");
			o.value = name;
			o.textContent = text;
			o.selected = name === value;
			select.appendChild(o);
		});
		select.onchange = () => onchange(select.value);
		return select;
	}

	render_actions() {
		if (this.tab !== "actions") return;
		const actions = genie.support_inbox.data.actions;
		this.list.innerHTML = "";
		if (!actions.length) {
			const none = document.createElement("div");
			none.className = "genie-sc-empty";
			none.textContent = __("Nothing needs you right now.");
			this.list.appendChild(none);
			return;
		}
		const intro = document.createElement("div");
		intro.className = "text-muted";
		intro.style.cssText = "font-size:12px;padding:0 10px 6px";
		intro.textContent = __("These tickets wait for you. Pick one to answer in its chat.");
		this.list.appendChild(intro);
		actions.forEach((t) =>
			this.list.appendChild(
				genie.inbox_item(t, () => this.show("tickets", t.name), { need: true })
			)
		);
	}
};
