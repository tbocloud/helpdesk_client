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
			if (opts.about) genie.support_chat.about(opts.about);
			else genie.support_chat.show(opts.tab, opts.ticket);
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
			.then(() => (opts.about ? this.about(opts.about) : this.show(opts.tab, opts.ticket)));
		window.addEventListener("resize", () => this.visible() && this.layout());
		frappe.router.on("change", () => this.visible() && this.layout());
	}

	visible() {
		return this.panel.style.display !== "none";
	}

	// Get help on a form (Phase 14): a new chat about the record, or about the error it showed.
	about(ctx) {
		this.show("chats", null, true);
		this.picked.chats = null;
		this.render_top();
		if (ctx.error) this.view.start_with_error(ctx);
		else this.view.start_about(ctx);
	}

	// Docked beside the page on wide screens (the page shrinks), over it below that and on the
	// point-of-sale and print pages. The width is the user's, remembered in this browser.
	layout() {
		const width = genie.panel_width();
		const dock = this.visible() && genie.should_dock();
		document.body.classList.toggle("genie-docked", dock);
		document.documentElement.style.setProperty(
			"--genie-docked-width",
			dock ? `${width}px` : "0px"
		);
		Object.assign(
			this.panel.style,
			dock
				? {
						top: "0",
						right: "0",
						bottom: "0",
						width: `${width}px`,
						maxWidth: "none",
						height: "auto",
						maxHeight: "none",
						border: "0",
						borderLeft: "1px solid var(--border-color, #e2e6e9)",
						borderRadius: "0",
						boxShadow: "none",
				  }
				: {
						top: "auto",
						right: "24px",
						bottom: "90px",
						width: `${width}px`,
						maxWidth: "calc(100vw - 32px)",
						height: "620px",
						maxHeight: "80vh",
						border: "1px solid var(--border-color, #e2e6e9)",
						borderRadius: "12px",
						boxShadow: "var(--shadow-lg, 0 8px 24px rgba(0,0,0,.18))",
				  }
		);
		// beside the page it is part of it; over the page it is a dialog
		this.panel.setAttribute("role", dock ? "complementary" : "dialog");
		this.resizer.setAttribute("aria-valuenow", String(width));
	}

	set_width(width) {
		genie.save_panel_width(width);
		this.layout();
	}

	add_resizer() {
		const handle = document.createElement("div");
		handle.className = "genie-sp-resize";
		handle.tabIndex = 0;
		handle.setAttribute("role", "separator");
		handle.setAttribute("aria-orientation", "vertical");
		handle.setAttribute("aria-label", __("Resize the Support panel"));
		handle.setAttribute("aria-valuemin", String(genie.PANEL_MIN));
		handle.setAttribute("aria-valuemax", String(genie.PANEL_MAX));
		handle.title = __("Drag to resize");
		handle.addEventListener("pointerdown", (e) => {
			e.preventDefault();
			const startX = e.clientX;
			const startWidth = genie.panel_width();
			document.body.style.userSelect = "none";
			const move = (ev) => this.set_width(startWidth + (startX - ev.clientX));
			const up = () => {
				window.removeEventListener("pointermove", move);
				window.removeEventListener("pointerup", up);
				document.body.style.userSelect = "";
			};
			window.addEventListener("pointermove", move);
			window.addEventListener("pointerup", up);
		});
		handle.addEventListener("keydown", (e) => {
			const step = e.shiftKey ? 64 : 16;
			if (e.key === "ArrowLeft") this.set_width(genie.panel_width() + step);
			else if (e.key === "ArrowRight") this.set_width(genie.panel_width() - step);
			else return;
			e.preventDefault();
		});
		this.panel.appendChild(handle);
		this.resizer = handle;
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
			// a screenshot or recording finished while the panel was closed
			reveal: () => this.show(),
		});
		this.add_resizer();
		panel.querySelector(".genie-sp-close").onclick = () => this.hide();
		// Esc closes the panel and goes back to the Support button (a dialog over it keeps its own Esc)
		panel.addEventListener("keydown", (e) => {
			if (e.key !== "Escape" || e.defaultPrevented) return;
			if (document.querySelector(".modal.show")) return;
			e.preventDefault();
			this.hide();
			// after Frappe's own Esc, which blurs whatever has focus
			setTimeout(() => {
				const fab = document.getElementById("genie-support-fab");
				if (fab) fab.focus();
			}, 0);
		});
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
		this.layout();
	}

	// tab: tickets / chats / actions; for tickets, which one to open; quiet: only switch the tab
	show(tab, ticket, quiet) {
		const data = genie.support_inbox.data;
		this.panel.style.display = "flex";
		this.layout();
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
		if (!changed || quiet) return;
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

genie.PANEL_MIN = 360;
genie.PANEL_MAX = 640;

genie.panel_width = function () {
	let width = 420;
	try {
		width = parseInt(localStorage.getItem("genie-panel-width"), 10) || 420;
	} catch (e) {
		// no storage in this browser: the default width
	}
	return Math.min(genie.PANEL_MAX, Math.max(genie.PANEL_MIN, width));
};

genie.save_panel_width = function (width) {
	width = Math.round(Math.min(genie.PANEL_MAX, Math.max(genie.PANEL_MIN, width)));
	try {
		localStorage.setItem("genie-panel-width", String(width));
	} catch (e) {
		// the panel still resizes for this page
	}
};

genie.should_dock = function () {
	const page = (frappe.get_route() || [])[0] || "";
	return (
		window.innerWidth >= 1280 &&
		// the Support page has the chat itself (the panel hides there); the till and print views need the width
		!["support-chat", "point-of-sale", "pos", "print", "printview"].includes(
			String(page).toLowerCase()
		)
	);
};
