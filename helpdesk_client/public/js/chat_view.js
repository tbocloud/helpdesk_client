// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// The support chat's shared parts (TBO Copilot Phase 13): the inbox (the user's tickets with their
// dots, the red ones again as actions, the chats that did not become tickets) and the chat view. The
// panel the Support button opens and the full page (/app/support-chat) both use them.

frappe.provide("genie");

genie.DOT_LABELS = {
	green: __("Fixed and confirmed"),
	red: __("Waiting for you"),
	orange: __("TBO Support is working on it"),
};
genie.DOT_EMOJI = { green: "🟢", red: "🔴", orange: "🟠" };

// The id of one message or ticket request (a uuid4 as 32 hex characters). It is made once and sent again
// with every retry of the same message, so TBO Support and this site take it once. getRandomValues works on
// plain-http sites too, where crypto.randomUUID does not.
genie.new_message_id = function () {
	const bytes = new Uint8Array(16);
	window.crypto.getRandomValues(bytes);
	bytes[6] = (bytes[6] & 0x0f) | 0x40;
	bytes[8] = (bytes[8] & 0x3f) | 0x80;
	return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
};

// The server's own words when it refused a call (Frappe's message), as plain text; "" when it gave none.
genie.server_message = function (r) {
	try {
		const messages = JSON.parse((r && r._server_messages) || "[]");
		const first = messages.length ? JSON.parse(messages[0]) : null;
		const text = first && typeof first === "object" ? first.message : first;
		// parsed in an inert document: nothing in it runs or loads
		return text
			? new DOMParser().parseFromString(String(text), "text/html").body.textContent.trim()
			: "";
	} catch (e) {
		return "";
	}
};

genie.dot = function (colour) {
	const span = document.createElement("span");
	span.className = `genie-sc-dot genie-sc-dot-${colour || "none"}`;
	if (colour) {
		span.title = genie.DOT_LABELS[colour];
		span.setAttribute("role", "img");
		span.setAttribute("aria-label", genie.DOT_LABELS[colour]);
	} else {
		span.setAttribute("aria-hidden", "true");
	}
	return span;
};

// One copy of the overview for the panel, the full page and the red button; it reloads when TBO
// Support changes a ticket or posts in a chat.
genie.support_inbox = {
	data: { tickets: [], actions: [], chats: [] },
	listeners: [],
	on(fn) {
		this.listeners.push(fn);
	},
	load() {
		if (this.loading) return this.loading;
		this.loading = frappe
			.xcall("helpdesk_client.inbox.overview")
			.then((data) => {
				this.data = data;
				frappe.boot.genie_actions_needed = data.actions.length;
				this.listeners.forEach((fn) => fn(data));
				return data;
			})
			.finally(() => {
				this.loading = null;
				if (this.stale) {
					this.stale = false;
					this.load().catch(() => null);
				}
			});
		return this.loading;
	},
	refresh_soon() {
		clearTimeout(this.timer);
		this.timer = setTimeout(() => {
			// a load already on its way may have read the overview before this change: one more after it
			if (this.loading) this.stale = true;
			this.load().catch(() => null);
		}, 500);
	},
	listen() {
		if (this.listening) return;
		this.listening = true;
		frappe.realtime.on("helpdesk_client_inbox", () => this.refresh_soon());
		frappe.realtime.on("helpdesk_client_chat", () => this.refresh_soon());
	},
};

genie.support_css = function () {
	if (document.getElementById("genie-sc-css")) return;
	const style = document.createElement("style");
	style.id = "genie-sc-css";
	style.textContent = `
		.genie-sc-dot{display:inline-block;width:10px;height:10px;border-radius:50%;flex:none;vertical-align:middle}
		.genie-sc-dot-green{background:var(--green-500,#2f9d5d)}
		.genie-sc-dot-red{background:var(--red-500,#e03636)}
		.genie-sc-dot-orange{background:var(--orange-500,#f08c00)}
		.genie-sc-dot-none{border:1px solid var(--gray-400,#c0c6cc)}
		.genie-sc-view{display:flex;flex-direction:column;flex:1;min-height:0}
		.genie-sc-head{display:flex;align-items:center;gap:8px;padding:12px 16px;border-bottom:1px solid var(--border-color,#e2e6e9);font-size:15px}
		.genie-sc-head b{white-space:nowrap}
		.genie-sc-head span.genie-sc-sum{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
		.genie-sc-status{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:8px 12px;border-bottom:1px solid var(--border-color,#e2e6e9);font-size:12px;background:var(--subtle-accent,#fafbfc)}
		.genie-sc-status-line{flex:1;min-width:150px}
		.genie-sc-body{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}
		.genie-sc-foot{border-top:1px solid var(--border-color,#e2e6e9);padding:8px;display:flex;flex-direction:column;gap:6px}
		.genie-sc-tools{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
		.genie-sc-closed{border-top:1px solid var(--border-color,#e2e6e9);padding:10px 12px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:12px}
		.genie-sc-closed span{flex:1;min-width:150px}
		.genie-sc-item{display:flex;align-items:flex-start;gap:8px;width:100%;text-align:left;padding:8px 10px;border:0;background:transparent;border-radius:8px;color:inherit;font-size:13px;cursor:pointer}
		.genie-sc-item:hover,.genie-sc-item:focus-visible,.genie-sc-item.active{background:var(--subtle-fg,#eef0f2)}
		.genie-sc-item .genie-sc-dot{margin-top:5px}
		.genie-sc-item-text{min-width:0;flex:1}
		.genie-sc-item-id{font-weight:600}
		.genie-sc-item-sub{display:block;color:var(--text-muted,#687178);font-size:12px;overflow:hidden;text-overflow:ellipsis}
		.genie-sc-item-need{display:block;color:var(--red-600,#c92a2a);font-size:12px}
		.genie-sc-empty{color:var(--text-muted,#687178);font-size:13px;padding:16px}
		.genie-support-open #genie-actions-btn{display:none!important}
		.genie-on-support-page #genie-actions-btn,.genie-on-support-page #genie-support-fab,.genie-on-support-page #genie-support-chat{display:none!important}
		.genie-sc-page .genie-sc-foot,.genie-sc-page .genie-sc-closed{padding-right:76px}
		.genie-sc-head small{color:var(--text-muted,#687178);font-size:12px;white-space:nowrap}
		.genie-sc-page{display:flex;height:calc(100vh - 170px);min-height:440px;border:1px solid var(--border-color,#e2e6e9);border-radius:12px;background:var(--card-bg,#fff);overflow:hidden}
		.genie-sc-rail{width:320px;flex:none;border-right:1px solid var(--border-color,#e2e6e9);padding:12px;overflow-y:auto;background:var(--subtle-accent,#fafbfc)}
		.genie-sc-rail-heading{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted,#687178);margin:16px 6px 4px}
		.genie-sc-main{flex:1;min-width:0;display:flex;flex-direction:column}
			.genie-sc-about{display:flex;align-items:center;gap:6px;padding:2px 2px 2px 10px;border:1px solid var(--border-color,#e2e6e9);border-radius:8px;background:var(--subtle-accent,#fafbfc);font-size:12px}
			.genie-sc-about span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
			.genie-sc-tray{display:flex;flex-wrap:wrap;gap:6px}
			.genie-sc-chip{display:inline-flex;align-items:center;gap:6px;max-width:100%;border:1px solid var(--border-color,#e2e6e9);border-radius:8px;padding:2px 2px 2px 8px;font-size:12px;background:var(--card-bg,#fff)}
			.genie-sc-chip-bad{border-color:var(--red-500,#e03636);background:var(--red-50,#fff0f0)}
			.genie-sc-chip-name{max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
			.genie-sc-chip-meta{color:var(--text-muted,#687178)}
			.genie-sc-chip-bad .genie-sc-chip-meta{color:var(--red-600,#c92a2a)}
			.genie-sc-chip button{border:0;background:transparent;min-width:28px;min-height:28px;border-radius:6px;cursor:pointer;color:inherit}
			.genie-sc-chip button:hover,.genie-sc-chip button:focus-visible{background:var(--subtle-fg,#eef0f2)}
			.genie-sc-tray-note{width:100%;color:var(--red-600,#c92a2a);font-size:12px}
			.genie-sc-similar{border:1px solid var(--border-color,#e2e6e9);border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;gap:6px;background:var(--card-bg,#fff);font-size:13px;max-width:95%}
			.genie-sc-similar-row{display:flex;flex-direction:column;align-items:flex-start;gap:4px;padding-top:8px;border-top:1px solid var(--border-color,#e2e6e9)}
			.genie-sc-similar-row .genie-sc-sub{color:var(--text-muted,#687178);font-size:12px}
			.genie-sc-record{font-size:12px;white-space:nowrap}
			#genie-recording-bar{position:fixed;bottom:24px;left:calc((100vw - var(--genie-docked-width,0px)) / 2);transform:translateX(-50%);z-index:1040;background:var(--card-bg,#fff);color:var(--text-color,#1f272e);border:1px solid var(--border-color,#e2e6e9);border-radius:12px;box-shadow:var(--shadow-lg,0 8px 24px rgba(0,0,0,.18));padding:8px 12px;width:max-content;max-width:calc(100vw - var(--genie-docked-width,0px) - 32px);font-size:13px}
			.genie-rb-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
			.genie-rb-dot{width:10px;height:10px;border-radius:50%;background:var(--red-500,#e03636);animation:genie-pulse 1.2s ease-in-out infinite}
			@keyframes genie-pulse{50%{opacity:.35}}
			@media (prefers-reduced-motion:reduce){.genie-rb-dot{animation:none}}
			.genie-rb-time{color:var(--text-muted,#687178);font-variant-numeric:tabular-nums}
			.genie-rb-ending{color:var(--red-600,#c92a2a);font-weight:600}
			.genie-rb-buttons{display:flex;gap:6px;margin-left:auto}
			.genie-rb-hint{color:var(--text-muted,#687178);font-size:12px;margin-top:2px}
			body.genie-docked{margin-right:var(--genie-docked-width,0px)}
			body.genie-docked #genie-support-fab{display:none!important}
			#genie-support-chat .genie-sp-resize{position:absolute;left:0;top:0;bottom:0;width:6px;cursor:col-resize;z-index:2;outline:none}
			#genie-support-chat .genie-sp-resize:hover,#genie-support-chat .genie-sp-resize:focus-visible{background:var(--primary,#2490ef);opacity:.45}
			.genie-support-strip{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:0 0 12px;padding:6px 12px;border:1px solid var(--blue-200,#c7dcff);background:var(--blue-50,#f0f6ff);border-radius:8px;font-size:13px}
			.genie-support-strip button{border:0;background:transparent;padding:4px 2px;text-decoration:underline;color:var(--text-color,#1f272e);cursor:pointer;display:inline-flex;align-items:center;gap:6px}
			.genie-error-note{margin-top:8px;font-size:12px;color:var(--text-muted,#687178)}
		@media (max-width:768px){
			.genie-sc-page{flex-direction:column;height:auto}
			.genie-sc-rail{width:auto;border-right:0;border-bottom:1px solid var(--border-color,#e2e6e9);max-height:45vh}
			.genie-sc-main{min-height:70vh}
		}`;
	document.head.appendChild(style);
};

genie.SupportChatView = class SupportChatView {
	// opts: on_open_ticket(name) when the user picks a ticket, on_ticket(name) when this chat became one,
	// on_chat(name) when a new chat started, on_new_chat() for the New chat button, show_head
	constructor(parent, opts = {}) {
		genie.support_css();
		this.opts = opts;
		this.conversation = null;
		this.ticket = null;
		this.busy = false;
		this.tray = []; // files waiting to go with the next message (Phase 14)
		this.pending = null; // Get help on a form: the chat starts on the first message
		this.draft = null; // the message being sent, with its id: the same id when it is sent again
		this.shown = new Set(); // the messages on screen, so one that comes twice shows once
		this.seq = 0; // which opening of the view is on screen: answers for an earlier one are not shown
		this.drafts = new Map(); // each chat's unsent words and files, while another chat is open
		this.build(parent);
		frappe.realtime.on("helpdesk_client_chat", (data) => {
			if (
				data &&
				data.conversation &&
				data.conversation === this.conversation &&
				data.message
			) {
				this.append(data.message);
			}
		});
	}

	build(parent) {
		const el = document.createElement("div");
		el.className = "genie-sc-view genie-no-record";
		el.innerHTML = `
			<div class="genie-sc-head" hidden></div>
			<div class="genie-sc-status" hidden></div>
			<div class="genie-sc-body" aria-live="polite"></div>
			<div class="genie-sc-foot" hidden>
				<div class="genie-sc-about" hidden></div>
				<div class="genie-sc-tray" hidden></div>
				<textarea class="form-control genie-sc-input" rows="2" placeholder="${__(
					"Write your message"
				)}" aria-label="${__(
			"Message"
		)}" style="resize:none;height:60px;min-height:60px"></textarea>
				<div class="genie-sc-tools">
					<button type="button" class="btn btn-xs btn-default genie-sc-attach">${__("Attach")}</button>
					<button type="button" class="btn btn-xs btn-default genie-sc-shot">${__("Screenshot")}</button>
					<button type="button" class="btn btn-xs btn-default genie-sc-record">${__(
						"Record screen"
					)}</button>
					<a href="#" class="genie-sc-form" style="font-size:12px;margin-left:auto">${__(
						"Send a form instead"
					)}</a>
					<button type="button" class="btn btn-xs btn-primary genie-sc-send">${__("Send")}</button>
				</div>
				<input type="file" class="genie-sc-file" accept="image/*,video/*,.pdf" style="display:none" multiple>
			</div>
			<div class="genie-sc-closed" hidden></div>`;
		parent.appendChild(el);
		this.el = el;
		this.head = el.querySelector(".genie-sc-head");
		this.status = el.querySelector(".genie-sc-status");
		this.body = el.querySelector(".genie-sc-body");
		this.about_box = el.querySelector(".genie-sc-about");
		this.tray_box = el.querySelector(".genie-sc-tray");
		this.record_btn = el.querySelector(".genie-sc-record");
		this.shot_btn = el.querySelector(".genie-sc-shot");
		this.foot = el.querySelector(".genie-sc-foot");
		this.closed = el.querySelector(".genie-sc-closed");
		this.input = el.querySelector(".genie-sc-input");
		this.file = el.querySelector(".genie-sc-file");
		el.querySelector(".genie-sc-send").onclick = () => this.send_text();
		el.querySelector(".genie-sc-attach").onclick = () => this.file.click();
		this.file.onchange = (e) => this.attach(e.target.files);
		this.shot_btn.onclick = () => this.screenshot();
		this.record_btn.onclick = () => this.record();
		el.querySelector(".genie-sc-form").onclick = (e) => {
			e.preventDefault();
			this.open_form();
		};
		// phones cannot capture the screen
		this.record_btn.hidden = this.shot_btn.hidden = !genie.can_record_screen();
		genie.screen_recorder.on_change((on) => {
			this.record_btn.textContent = on ? "■ " + __("Stop recording") : __("Record screen");
		});
		this.input.addEventListener("keydown", (e) => {
			// an Enter that ends typing with an input method (Chinese, Japanese and others) is not a send;
			// Safari marks that Enter with keyCode 229 only
			if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
				e.preventDefault();
				this.send_text();
			}
		});
	}

	call(method, args) {
		return frappe.xcall(`helpdesk_client.${method}`, args);
	}

	// A message to TBO Support: a refusal comes back as an Error with the server's own words, shown in the
	// chat instead of a pop-up.
	send_call(args) {
		return new Promise((resolve, reject) => {
			const request = frappe.call({
				method: "helpdesk_client.chat.send",
				type: "POST",
				args,
				silent: true,
				callback: (r) => resolve(r.message),
				error: (r) => reject(new Error(genie.server_message(r))),
			});
			// Frappe answers some failures itself (a deadlock or a timeout on the server) without calling
			// `error`: the request's own failure ends the send then. It runs after Frappe's, and a promise
			// settles once, so what `error` gave stays when it was called.
			if (request && typeof request.fail === "function") {
				request.fail((xhr) =>
					reject(new Error(genie.server_message(xhr && xhr.responseJSON)))
				);
			}
		});
	}

	// --- what the view shows ----------------------------------------------------------------------

	// Empties the view for what opens next, and returns that opening's number: an answer that comes back
	// when another one is on screen is dropped.
	waiting() {
		this.keep_draft();
		this.conversation = null;
		this.ticket = null;
		this.pending = null;
		this.draft = null;
		this.status_closed = false;
		this.render_about();
		this.body.innerHTML = "";
		this.shown.clear();
		this.head.hidden = this.status.hidden = this.foot.hidden = this.closed.hidden = true;
		this.typing(true, __("Loading…"));
		return ++this.seq;
	}

	async open_ticket(name) {
		const seq = this.waiting();
		try {
			const r = await this.call("chat.open_ticket", { ticket: name });
			if (seq === this.seq) this.render(r);
		} catch (e) {
			if (seq === this.seq) this.unavailable();
		}
	}

	async open_chat(name) {
		const seq = this.waiting();
		try {
			const r = await this.call("chat.history", { conversation: name });
			if (seq === this.seq) this.render(r);
		} catch (e) {
			if (seq === this.seq) this.unavailable();
		}
	}

	// A new chat checks first that it is a new problem, not one of the user's open tickets.
	async start_new(checked) {
		const seq = this.waiting();
		if (!checked) {
			const data = await genie.support_inbox.load().catch(() => null);
			if (seq !== this.seq) return; // something else was opened meanwhile
			const open = data ? data.tickets.filter((t) => !t.closed) : [];
			if (open.length) return this.ask_new_or_ticket(open);
		}
		try {
			const r = await this.call("chat.start", { ...genie.capture_context(), new: 1 });
			genie.support_inbox.refresh_soon();
			// something else was opened meanwhile: the new chat waits in the list
			if (seq !== this.seq) return;
			this.render(r);
			if (this.opts.on_chat) this.opts.on_chat(r.conversation);
		} catch (e) {
			if (seq === this.seq) this.unavailable();
		}
	}

	ask_new_or_ticket(open) {
		this.waiting();
		this.typing(false);
		const box = document.createElement("div");
		box.style.cssText = "display:flex;flex-direction:column;gap:6px";
		const q = document.createElement("div");
		q.style.cssText = "font-weight:600;font-size:13px";
		q.textContent = __("Is this a new problem, or about one of your open tickets?");
		const hint = document.createElement("div");
		hint.className = "text-muted";
		hint.style.fontSize = "12px";
		hint.textContent = __(
			"If it continues a ticket, pick it: the team sees it there with everything said so far."
		);
		box.append(q, hint);
		open.forEach((t) => box.appendChild(genie.inbox_item(t, () => this.pick_ticket(t.name))));
		const fresh = document.createElement("button");
		fresh.type = "button";
		fresh.className = "btn btn-sm btn-primary";
		fresh.style.alignSelf = "flex-start";
		fresh.textContent = __("It's a new problem");
		fresh.onclick = () => this.start_new(true);
		box.appendChild(fresh);
		this.body.appendChild(box);
	}

	pick_ticket(name) {
		if (this.opts.on_open_ticket) this.opts.on_open_ticket(name);
		else this.open_ticket(name);
	}

	render(r) {
		this.typing(false);
		this.conversation = r.conversation || null;
		this.ticket = r.ticket_state || null;
		if (this.conversation) this.restore_draft(this.conversation);
		this.body.innerHTML = "";
		this.shown.clear();
		if (!this.ticket && r.conversation) this.body.appendChild(this.automated_note());
		(r.messages || []).forEach((m) => this.append(m));
		if (r.note) this.append({ direction: "System", kind: "Text", text: r.note });
		this.render_head();
		this.render_status();
		this.status_closed = !this.ticket && r.status === "Closed";
		this.render_foot(!!r.read_only);
		this.scroll();
		if (!this.foot.hidden) this.input.focus();
	}

	render_head() {
		this.head.innerHTML = "";
		this.head.hidden = !(this.opts.show_head && this.ticket);
		if (this.head.hidden) return;
		const id = document.createElement("b");
		id.textContent = this.ticket.name;
		const sum = document.createElement("span");
		sum.className = "genie-sc-sum";
		sum.textContent = "· " + (this.ticket.summary || "");
		this.head.append(genie.dot(this.ticket.dot), id, sum);
		if (this.ticket.ticket_id) {
			// the number TBO Support's messages and emails use
			const number = document.createElement("small");
			number.textContent = __("TBO Support #{0}", [this.ticket.ticket_id]);
			this.head.appendChild(number);
		}
	}

	render_status() {
		this.status.innerHTML = "";
		this.status.hidden = !this.ticket;
		if (!this.ticket) return;
		const line = document.createElement("span");
		line.className = "genie-sc-status-line";
		line.textContent = this.ticket.line;
		this.status.append(genie.dot(this.ticket.dot), line);
		if (this.ticket.confirm) {
			this.status.append(
				this.button(__("It's fixed"), "btn-primary", () => this.answer_fix(true)),
				this.button(__("Still broken"), "btn-default", () => this.answer_fix(false))
			);
		}
		if (this.ticket.record) {
			const rec = this.ticket.record;
			const a = document.createElement("a");
			a.href = `/app/${frappe.router.slug(rec.doctype)}/${encodeURIComponent(rec.name)}`;
			a.className = "genie-sc-record";
			a.textContent = `📄 ${__(rec.doctype)} ${rec.name}`;
			a.title = __("Open {0}", [`${__(rec.doctype)} ${rec.name}`]);
			a.onclick = (e) => {
				e.preventDefault();
				frappe.set_route("Form", rec.doctype, rec.name);
			};
			this.status.appendChild(a);
		}
		if (this.ticket.following) {
			const you = document.createElement("span");
			you.className = "text-muted";
			you.textContent = __("You follow this ticket");
			this.status.appendChild(you);
			return;
		}
		this.status.append(
			this.button(__("What's the status?"), "btn-default", () => this.ask_status())
		);
	}

	render_foot(read_only) {
		const closed = !!(this.ticket && this.ticket.closed);
		this.foot.hidden = read_only || closed || this.status_closed || !this.conversation;
		// phones cannot capture the screen (checked again: the panel may have been made on a wider screen)
		this.record_btn.hidden = this.shot_btn.hidden = !genie.can_record_screen();
		this.closed.innerHTML = "";
		this.closed.hidden = !(closed || this.status_closed);
		if (this.status_closed && !closed) {
			// a chat that ended without a ticket (answered, or joined a colleague's ticket)
			const done = document.createElement("span");
			done.textContent = __("This chat has ended.");
			this.closed.append(
				done,
				this.button(__("New chat"), "btn-primary", () =>
					this.opts.on_new_chat ? this.opts.on_new_chat() : this.start_new()
				)
			);
			return;
		}
		if (!closed) return;
		const text = document.createElement("span");
		text.textContent = __(
			"This ticket is closed. Is the problem back, or is it something new?"
		);
		this.closed.append(
			text,
			this.button(__("It came back"), "btn-default", () =>
				this.answer_fix(false, __("What came back?"))
			),
			this.button(__("New chat"), "btn-primary", () =>
				this.opts.on_new_chat ? this.opts.on_new_chat() : this.start_new()
			)
		);
	}

	// Who answers, and what goes with each message (Phase 23 B14): said once, above the chat.
	automated_note() {
		const note = document.createElement("div");
		note.className = "text-muted";
		note.style.cssText = "font-size:12px;padding:0 2px 4px";
		note.textContent = __(
			"You are chatting with TBO Copilot, an automated assistant; a person from TBO Support takes over when needed. With your messages TBO Support gets the page you are on, your roles, your error messages of the last day and this site's app versions."
		);
		return note;
	}

	button(label, style, onclick) {
		const b = document.createElement("button");
		b.type = "button";
		b.className = `btn btn-xs ${style}`;
		b.textContent = label;
		b.onclick = onclick;
		return b;
	}

	unavailable() {
		this.typing(false);
		this.body.innerHTML = "";
		const div = document.createElement("div");
		div.style.cssText = "padding:12px;font-size:13px";
		div.innerHTML = `<p>${__("The support chat is not available right now.")}</p>`;
		div.appendChild(
			this.button(__("Send a form instead"), "btn-primary", () => this.open_form())
		);
		this.body.appendChild(div);
	}

	// The line under the chat while something is on its way; `label` replaces the usual words.
	typing(on, label) {
		let dot = this.body.querySelector(".genie-chat-typing");
		if (on && !dot) {
			dot = document.createElement("div");
			dot.className = "genie-chat-typing text-muted";
			dot.style.fontSize = "12px";
			// a ticket's chat goes to people; before that the assistant answers, and says it is one
			dot.textContent =
				label ||
				(this.ticket
					? __("Sending to TBO Support…")
					: __("TBO Copilot, an automated assistant, is writing…"));
			this.body.appendChild(dot);
		} else if (!on && dot) {
			dot.remove();
		}
		this.scroll();
	}

	scroll() {
		this.body.scrollTop = this.body.scrollHeight;
	}

	append(message) {
		if (message.name) {
			// the same message can come in the answer and live (or again, after a retry)
			if (this.shown.has(message.name)) return null;
			this.shown.add(message.name);
		}
		const mine = message.direction === "Customer";
		const wrap = document.createElement("div");
		wrap.style.cssText = `display:flex;flex-direction:column;align-items:${
			mine ? "flex-end" : "flex-start"
		}`;
		const bubble = document.createElement("div");
		const look = mine
			? "background:var(--blue-100,#e6f0ff)"
			: message.kind === "Stage"
			? "background:var(--yellow-50,#fffbea);border:1px solid var(--yellow-200,#fbe7a3)"
			: message.kind === "Status"
			? "background:var(--blue-50,#f0f6ff);border:1px solid var(--blue-200,#c7dcff)"
			: "background:var(--subtle-fg,#f4f5f6)";
		bubble.style.cssText = `max-width:85%;padding:8px 10px;border-radius:10px;font-size:13px;white-space:pre-wrap;word-wrap:break-word;${look}`;
		const card = message.card || {};
		if (card.title) {
			const title = document.createElement("div");
			title.style.fontWeight = "600";
			title.textContent = card.title;
			bubble.appendChild(title);
		}
		const lines =
			card.lines && card.lines.length ? card.lines : message.text ? [message.text] : [];
		lines.forEach((line) => {
			const p = document.createElement("div");
			p.textContent = line;
			bubble.appendChild(p);
		});
		if (card.facts && card.facts.length) {
			const dl = document.createElement("dl");
			dl.style.cssText = "margin:6px 0 0;font-size:12px";
			card.facts.forEach(([k, v]) => {
				const dt = document.createElement("dt");
				dt.style.cssText = "color:var(--text-muted,#687178);font-weight:normal";
				dt.textContent = k;
				const dd = document.createElement("dd");
				dd.style.margin = "0 0 4px";
				dd.textContent = v;
				dl.append(dt, dd);
			});
			bubble.appendChild(dl);
		}
		(card.links || []).forEach(([label, url]) => {
			if (!/^https?:\/\//.test(url || "")) return;
			const a = document.createElement("a");
			a.href = url;
			a.target = "_blank";
			a.rel = "noopener noreferrer";
			a.textContent = label;
			a.style.display = "block";
			bubble.appendChild(a);
		});
		(message.files || []).forEach((f) => {
			const span = document.createElement("div");
			span.className = "text-muted";
			span.style.fontSize = "12px";
			span.textContent = "📎 " + (f.file_name || f.file_url);
			bubble.appendChild(span);
		});
		wrap.appendChild(bubble);
		// once the chat is a ticket, only the fix's own buttons still mean something
		const actions = (card.actions || []).filter(
			(a) => !this.ticket || ["fixed", "still_broken"].includes(a.verb)
		);
		if (actions.length && this.conversation && !(this.ticket && this.ticket.closed)) {
			const row = document.createElement("div");
			row.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin-top:6px";
			const ids = {}; // one id per button of this card, the same when it is pressed again
			actions.forEach((a) => {
				const b = this.button(
					a.label,
					a.style === "positive" ? "btn-primary" : "btn-default",
					async () => {
						const buttons = row.querySelectorAll("button");
						buttons.forEach((x) => (x.disabled = true));
						// it did not go (or a recording did not start): the buttons work again
						if (!(await this.act(a.verb, ids)))
							buttons.forEach((x) => (x.disabled = false));
					}
				);
				row.appendChild(b);
			});
			wrap.appendChild(row);
		}
		const typing = this.body.querySelector(".genie-chat-typing");
		this.body.insertBefore(wrap, typing || null);
		this.scroll();
		if (message.kind === "Summary" && !this.ticket && this.conversation) {
			this.maybe_similar(wrap);
		}
		return wrap;
	}

	// Before a new ticket is raised: colleagues' open tickets that look the same (Phase 14).
	async maybe_similar(summary) {
		const conversation = this.conversation;
		if (this.similar_for === conversation) return;
		this.similar_for = conversation;
		let rows = [];
		try {
			rows = await this.call("similar.similar", { conversation });
		} catch (e) {
			return;
		}
		if (!rows.length || this.conversation !== conversation || !summary.isConnected) return;
		const box = document.createElement("section");
		box.className = "genie-sc-similar";
		box.setAttribute("aria-label", __("Similar open tickets at your company"));
		const title = document.createElement("b");
		title.textContent = __("Similar open tickets at your company");
		const hint = document.createElement("div");
		hint.className = "text-muted";
		hint.style.fontSize = "12px";
		hint.textContent = __(
			"If one of these is your problem, follow it instead of raising a new ticket."
		);
		box.append(title, hint);
		rows.forEach((t) => {
			const row = document.createElement("div");
			row.className = "genie-sc-similar-row";
			const head = document.createElement("div");
			head.style.cssText = "display:flex;align-items:center;gap:6px";
			const id = document.createElement("b");
			id.textContent = t.name;
			const sum = document.createElement("span");
			sum.textContent = t.summary;
			head.append(genie.dot(t.dot), id, sum);
			const sub = document.createElement("span");
			sub.className = "genie-sc-sub";
			sub.textContent = `${t.line} · ${
				t.colleagues === 1
					? __("1 colleague affected")
					: __("{0} colleagues affected", [t.colleagues])
			}`;
			const join = this.button(__("This is my issue, add me to it"), "btn-primary", () =>
				this.join(t.name, box)
			);
			row.append(head, sub, join);
			box.appendChild(row);
		});
		const different = document.createElement("div");
		different.className = "text-muted";
		different.style.fontSize = "12px";
		different.textContent = __("Mine is different: raise the ticket below.");
		box.appendChild(different);
		this.body.insertBefore(box, summary);
		genie.announce(__("{0} similar open tickets found.", [rows.length]));
	}

	async join(ticket, box) {
		const seq = this.seq;
		box.querySelectorAll("button").forEach((b) => (b.disabled = true));
		let r;
		try {
			r = await this.call("similar.join", { conversation: this.conversation, ticket });
		} catch (e) {
			box.querySelectorAll("button").forEach((b) => (b.disabled = false));
			return;
		}
		genie.support_inbox.refresh_soon();
		if (seq !== this.seq) return; // another chat is open now: only the list follows
		(r.messages || []).forEach((m) => this.append(m));
		const open = this.button(__("Open {0}", [ticket]), "btn-default", () =>
			this.pick_ticket(ticket)
		);
		open.style.alignSelf = "flex-start";
		this.body.appendChild(open);
		if (r.told) {
			this.status_closed = true;
			this.render_foot(false);
		}
		this.scroll();
	}

	// --- what the user does -----------------------------------------------------------------------

	// One message or button press to TBO Support. Its answer, or null when it did not go: then a line in the
	// chat says why (the server's own words), and nothing shows as sent.
	async post(args) {
		if (!this.conversation || this.busy) return null;
		const seq = this.seq;
		this.busy = true;
		this.typing(true);
		let r = null;
		let why = "";
		try {
			r = await this.send_call({ conversation: this.conversation, ...args });
		} catch (e) {
			why = (e && e.message) || "";
		} finally {
			this.busy = false;
			if (seq === this.seq) this.typing(false);
		}
		if (r && r.ok === false) {
			why = r.error || "";
			r = null;
		}
		if (seq !== this.seq) {
			// another chat is open now: the list follows, and nothing of this one shows in it
			genie.support_inbox.refresh_soon();
			if (!r) {
				frappe.show_alert({
					indicator: "red",
					message: frappe.utils.escape_html(
						__("Not sent in the chat you left: {0}", [
							why || __("TBO Support could not be reached. Try again in a moment."),
						])
					),
				});
			}
			return r;
		}
		if (!r) {
			this.append({
				direction: "System",
				kind: "Text",
				text: why
					? __("Not sent: {0}", [why])
					: __("Not sent: TBO Support could not be reached. Try again in a moment."),
			});
			return null;
		}
		(r.messages || []).forEach((m) => this.append(m));
		genie.support_inbox.refresh_soon();
		if (r.ticket && !this.ticket) {
			// the chat became a ticket: from now on it is shown under the ticket's name
			if (this.opts.on_ticket) this.opts.on_ticket(r.ticket);
			else this.open_ticket(r.ticket);
		} else if (this.ticket && ["fixed", "still_broken"].includes(args.action)) {
			this.open_ticket(this.ticket.name);
		} else if (r.status === "Closed" && !this.ticket) {
			// answered, or joined a colleague's ticket: the chat ends, and typing more would go nowhere
			this.status_closed = true;
			this.render_foot(false);
		}
		return r;
	}

	// What is typed and attached belongs to the chat it was written in: leaving that chat keeps it aside,
	// with the id of a message on its way (a retry reuses it), and an empty box and tray are what the next
	// chat gets. A chat not started yet keeps its own draft too, under null.
	keep_draft() {
		const text = this.input.value || "";
		if (text.trim() || this.tray.length || this.draft) {
			this.drafts.set(this.conversation || null, {
				text,
				tray: this.tray,
				draft: this.draft,
			});
		}
		this.input.value = "";
		this.tray = [];
		this.render_tray();
	}

	restore_draft(key = this.conversation) {
		const kept = this.drafts.get(key || null);
		if (!kept) return;
		this.drafts.delete(key || null);
		this.input.value = kept.text;
		this.tray = kept.tray;
		this.draft = kept.draft || null;
		this.render_tray();
	}

	// Words and files go back to a chat that is not open now: the words before what its draft holds,
	// the files into its tray; the id of its message on its way stays.
	keep_for(conversation, { text = "", items = [] } = {}) {
		const kept = this.drafts.get(conversation || null) || { text: "", tray: [], draft: null };
		this.drafts.set(conversation || null, {
			text: [text, kept.text.trim()].filter(Boolean).join("\n"),
			tray: kept.tray.concat(items.filter((f) => !kept.tray.includes(f))),
			draft: kept.draft,
		});
	}

	// Words that were not sent go back into the box, before what was typed since.
	back_in_box(text) {
		const typed = (this.input.value || "").trim();
		this.input.value = typed ? `${text}\n${typed}` : text;
		this.input.focus();
	}

	// The message's id: the same while the same text and files are sent again after a failure.
	message_id(text, files) {
		const key = JSON.stringify([this.conversation, text, files.map((f) => f.file_url)]);
		if (!this.draft || this.draft.key !== key) {
			this.draft = { key, id: genie.new_message_id() };
		}
		return this.draft.id;
	}

	async send_text() {
		const text = (this.input.value || "").trim();
		if (this.busy || (!text && !this.tray.length)) return;
		if (this.tray.some((f) => f.error)) return;
		const seq = this.seq; // the chat this message is for
		if (this.pending) await this.begin_about();
		if (seq !== this.seq || !this.conversation) return;
		const conversation = this.conversation;
		const items = this.tray.slice(); // the files that go with it
		// the words being sent leave the box now: what is typed while they go is the next message
		this.input.value = "";
		let files = [];
		if (items.length) {
			this.busy = true;
			this.typing(true, __("Uploading…"));
			files = await this.upload_tray(items);
			this.busy = false;
			if (seq !== this.seq) {
				// another chat was opened while the files went up: nothing goes to it unasked; the words wait
				// with their chat (its files are in its draft already)
				if (conversation === this.conversation) this.back_in_box(text);
				else this.keep_for(conversation, { text });
				frappe.show_alert({
					indicator: "orange",
					message: __(
						"Not sent: another chat was opened. Your message waits in the chat you wrote it in."
					),
				});
				return;
			}
			this.typing(false);
			if (!files) {
				this.back_in_box(text);
				frappe.show_alert({
					indicator: "red",
					message: __("A file could not be uploaded. Try again."),
				});
				return;
			}
		}
		const client_message_id = this.message_id(text, files);
		const mine = this.append({ direction: "Customer", kind: "Text", text, files });
		const r = await this.post(
			files.length
				? { text, files: JSON.stringify(files), client_message_id }
				: { text, client_message_id }
		);
		if (seq !== this.seq && conversation !== this.conversation) {
			// another chat is open now: the message's chat keeps its own draft, never this box. Sent: its
			// files and message id leave that draft. Not sent: the words wait there, with the same id.
			if (!r) return this.keep_for(conversation, { text });
			const kept = this.drafts.get(conversation);
			if (kept) {
				kept.tray = kept.tray.filter((f) => !items.includes(f));
				kept.draft = null;
				if (!kept.text.trim() && !kept.tray.length) this.drafts.delete(conversation);
			}
			return;
		}
		if (r) {
			this.draft = null;
			this.tray = this.tray.filter((f) => !items.includes(f));
			this.render_tray();
			return;
		}
		// not sent: it comes off the chat and back into the box (its files stay in the tray), ready to send again
		if (mine) mine.remove();
		this.back_in_box(text);
	}

	// A card's button. True when it went (or the recording started); false and the buttons work again when not.
	async act(verb, ids = {}) {
		if (verb === "record") {
			// a recording already running keeps the chat it was started for: this press only stops it
			if (genie.screen_recorder.recording()) return this.record();
			// TBO Support asked for it in this chat: the recording goes to it as soon as the user stops
			const started = await this.record(this.conversation);
			if (!started) {
				this.append({
					direction: "System",
					kind: "Text",
					text: __(
						"The recording did not start. Press Record to try again, or Not now to go on without it."
					),
				});
			}
			return started;
		}
		if (verb === "fixed") return this.answer_fix(true);
		if (verb === "still_broken") return this.answer_fix(false);
		ids[verb] = ids[verb] || genie.new_message_id();
		return !!(await this.post({ action: verb, client_message_id: ids[verb] }));
	}

	// It's fixed / Still broken / It came back: recorded on the ticket, so its dot changes at once.
	// True once it is recorded.
	answer_fix(fixed, question) {
		const go = (note) => {
			if (this.conversation)
				return this.post({ action: fixed ? "fixed" : "still_broken", note }).then(
					(r) => !!r
				);
			const method = fixed ? "confirm_resolution" : "reopen";
			const seq = this.seq;
			const ticket = this.ticket.name;
			return frappe
				.xcall(
					`helpdesk_client.helpdesk_client.doctype.support_ticket.support_ticket.${method}`,
					{
						ticket,
						note,
					}
				)
				.then(() => {
					genie.support_inbox.refresh_soon();
					if (seq === this.seq) this.open_ticket(ticket);
					return true;
				})
				.catch(() => false);
		};
		if (fixed) return go("");
		return new Promise((resolve) => {
			let answered = false;
			const d = frappe.prompt(
				{
					fieldname: "note",
					fieldtype: "Small Text",
					label: question || __("What is still wrong?"),
					reqd: 1,
				},
				(v) => {
					answered = true;
					go(v.note).then(resolve);
				},
				__("Tell TBO Support"),
				__("Send")
			);
			// closed without sending: nothing happened
			const onhide = d.onhide;
			d.onhide = () => {
				if (onhide) onhide();
				setTimeout(() => !answered && resolve(false), 0);
			};
		});
	}

	async ask_status() {
		if (!this.ticket) return;
		const seq = this.seq;
		let message;
		try {
			message = await this.call("inbox.ticket_status", { ticket: this.ticket.name });
		} catch (e) {
			message = {
				direction: "System",
				kind: "Text",
				text: __("The status could not be read just now."),
			};
		}
		if (seq === this.seq) this.append(message); // not in another ticket opened meanwhile
	}

	// --- files waiting in the message box (Phase 14) ---------------------------------------------

	attach(fileList) {
		Array.from(fileList || [])
			.slice(0, 5)
			.forEach((file) => {
				const kind = file.type.startsWith("video/")
					? "video"
					: file.type.startsWith("image/")
					? "image"
					: "file";
				this.add_to_tray({ blob: file, name: file.name, kind, size: file.size });
			});
		this.file.value = "";
	}

	add_to_tray(item) {
		const limit =
			item.kind === "video"
				? genie.screen_recorder.cap_bytes()
				: frappe.boot.max_file_size || 25 * 1024 * 1024;
		if (item.size > limit) {
			item.error = __("Too large. Files can be up to {0}.", [genie.format_bytes(limit)]);
		}
		this.tray.push(item);
		this.render_tray();
		this.input.focus();
	}

	render_tray() {
		const box = this.tray_box;
		box.innerHTML = "";
		box.hidden = !this.tray.length;
		this.tray.forEach((item, i) => {
			const chip = document.createElement("span");
			chip.className = "genie-sc-chip" + (item.error ? " genie-sc-chip-bad" : "");
			const name = document.createElement("span");
			name.className = "genie-sc-chip-name";
			name.textContent = `${{ image: "🖼", video: "🎬" }[item.kind] || "📄"} ${item.name}`;
			name.title = item.name;
			const meta = document.createElement("span");
			meta.className = "genie-sc-chip-meta";
			meta.textContent =
				item.error ||
				[
					item.seconds ? genie.format_seconds(item.seconds) : "",
					genie.format_bytes(item.size),
				]
					.filter(Boolean)
					.join(" · ");
			chip.append(name, meta);
			if (!item.error && (item.kind === "image" || item.kind === "video")) {
				const play = document.createElement("button");
				play.type = "button";
				play.textContent = item.kind === "video" ? "▶" : "👁";
				play.setAttribute(
					"aria-label",
					item.kind === "video"
						? __("Play {0}", [item.name])
						: __("View {0}", [item.name])
				);
				play.onclick = () => this.preview(item);
				chip.appendChild(play);
			}
			const remove = document.createElement("button");
			remove.type = "button";
			remove.textContent = "×";
			remove.setAttribute("aria-label", __("Remove {0}", [item.name]));
			remove.onclick = () => {
				this.tray.splice(i, 1);
				this.render_tray();
			};
			chip.appendChild(remove);
			box.appendChild(chip);
		});
		if (this.tray.some((f) => f.error)) {
			const note = document.createElement("div");
			note.className = "genie-sc-tray-note";
			note.setAttribute("role", "alert");
			note.textContent = __(
				"Remove the file marked in red to send. For a longer video, record a shorter one or share a link."
			);
			box.appendChild(note);
		}
	}

	preview(item) {
		const url = URL.createObjectURL(item.blob);
		// the dialog's title is HTML: the file's name shows as written
		const d = new frappe.ui.Dialog({
			title: frappe.utils.escape_html(item.name),
			size: "large",
		});
		const media = document.createElement(item.kind === "video" ? "video" : "img");
		media.src = url;
		media.style.cssText =
			"width:100%;max-height:60vh;border-radius:8px;background:#000;object-fit:contain";
		if (item.kind === "video") media.controls = true;
		else media.alt = item.name;
		d.body.appendChild(media);
		d.onhide = () => URL.revokeObjectURL(url);
		d.show();
	}

	// Each file is uploaded once: after a failed send it stays in the tray with its address, ready to go again.
	async upload_tray(items) {
		const files = [];
		for (const item of items) {
			if (!item.file_url) {
				item.file_url = await genie
					.UploadFile(item.blob, item.name, { is_private: 1 })
					.catch(() => null);
			}
			if (!item.file_url) return null;
			files.push({ file_url: item.file_url, file_name: item.name });
		}
		return files;
	}

	async screenshot() {
		const blob = await genie.capture_screenshot();
		if (!blob) return;
		if (this.opts.reveal) this.opts.reveal();
		this.add_to_tray({
			blob,
			name: `screenshot-${Date.now()}.png`,
			kind: "image",
			size: blob.size,
		});
	}

	// True when a recording started (or one was stopped); false when the user cancelled or said no in the
	// browser's prompt. What is shared and who can watch it is said first, and the voice is off unless chosen.
	// asked: the chat that asked for the recording; it is bound to this recording when it starts
	async record(asked = null) {
		if (genie.screen_recorder.recording()) {
			genie.screen_recorder.stop();
			return true;
		}
		if (!genie.can_record_screen()) {
			frappe.msgprint(
				__("This browser cannot record the screen; you can attach a screenshot instead.")
			);
			return false;
		}
		const choice = await genie.recording_choice();
		if (!choice) return false;
		return genie.screen_recorder.start((file) => this.recorded(file, asked), choice);
	}

	recorded(file, asked) {
		if (this.opts.reveal) this.opts.reveal();
		// it goes at once only to the chat that asked for it, while that chat is still open; otherwise it
		// waits in the tray, to go when the user sends it
		if (asked && asked === this.conversation) return this.post_recording(file);
		if (asked) {
			// asked for in a chat that is not open now: it waits in that chat's own draft, never in this one
			this.keep_for(asked, { items: [file] });
			frappe.show_alert({
				indicator: "blue",
				message: __("The recording waits in the chat that asked for it. Open it to send."),
			});
			return;
		}
		this.add_to_tray(file);
	}

	async post_recording(file) {
		const conversation = this.conversation;
		const url = await genie
			.UploadFile(file.blob, file.name, { is_private: 1 })
			.catch(() => null);
		if (!url) return this.keep_recording(conversation, file);
		// another chat was opened while it went up: it waits with its own chat (uploaded already)
		if (this.conversation !== conversation)
			return this.keep_recording(conversation, { ...file, file_url: url });
		const files = [{ file_url: url, file_name: file.name }];
		const mine = this.append({ direction: "Customer", kind: "Text", text: "", files });
		const r = await this.post({
			action: "recorded",
			files: JSON.stringify(files),
			client_message_id: genie.new_message_id(),
		});
		if (!r) {
			// not sent: the recording waits with its chat (uploaded already) to go with the next message
			if (mine) mine.remove();
			this.keep_recording(conversation, { ...file, file_url: url });
		}
	}

	// A recording that could not go yet waits with the chat that asked for it: in the tray while that chat
	// is open, in its draft while another one is.
	keep_recording(conversation, file) {
		if (conversation === this.conversation) return this.add_to_tray(file);
		this.keep_for(conversation, { items: [file] });
	}

	// --- Get help on a form (Phase 14) ---------------------------------------------------------------

	// The chat starts on the record with the user's first message; the record can be removed before.
	start_about(record) {
		this.waiting();
		this.typing(false);
		this.restore_draft(null); // what was written for a chat not started yet
		this.pending = { record };
		this.render_about();
		this.foot.hidden = false;
		this.body.appendChild(this.automated_note());
		const hint = document.createElement("div");
		hint.className = "genie-sc-empty";
		hint.textContent =
			record && record.name
				? __(
						"Tell TBO Support what happened on {0}. Your message goes with the record's name.",
						[record.name]
				  )
				: __("Tell TBO Support what happened.");
		this.body.appendChild(hint);
		this.input.focus();
	}

	render_about() {
		const box = this.about_box;
		if (!box) return;
		box.innerHTML = "";
		const record = this.pending && this.pending.record;
		box.hidden = !record;
		this.input.placeholder = record
			? record.name
				? __("What happened on {0}?", [record.name])
				: __("What happened?")
			: __("Write your message");
		if (!record) return;
		const what = `${__(record.doctype)} ${record.name || ""}`.trim();
		const label = document.createElement("span");
		label.textContent = `📄 ${__("About")} ${what}`;
		const x = document.createElement("button");
		x.type = "button";
		x.className = "btn btn-xs btn-default";
		x.textContent = "×";
		x.title = __("Don't include {0}", [what]);
		x.setAttribute("aria-label", __("Don't include {0}", [what]));
		x.onclick = () => {
			this.pending.record = null;
			this.render_about();
			this.input.focus();
		};
		box.append(label, x);
	}

	// The record stays with the message until the chat has started: a failed start can be sent again, or
	// sent as a form, with it.
	async begin_about() {
		const record = this.pending ? this.pending.record : null;
		const seq = this.seq;
		this.busy = true; // one start, however often Send is pressed
		this.typing(true);
		try {
			const r = await this.call("chat.start", {
				page_route: (record && record.page_route) || genie.capture_context().page_route,
				ref_doctype: record ? record.doctype : "",
				ref_docname: record ? record.name || "" : "",
				new: 1,
			});
			genie.support_inbox.refresh_soon();
			// something else was opened meanwhile: the new chat waits in the list
			if (seq !== this.seq) return;
			this.pending = null;
			this.render_about();
			this.render(r);
			if (this.opts.on_chat) this.opts.on_chat(r.conversation);
		} catch (e) {
			if (seq === this.seq) this.unavailable();
		} finally {
			this.busy = false;
		}
	}

	// Get help with this error: the record and the error go at once, and TBO Support takes them as facts.
	async start_with_error(ctx) {
		const seq = this.waiting();
		try {
			const r = await this.call("chat.start", {
				page_route: ctx.page_route || "",
				ref_doctype: ctx.doctype || "",
				ref_docname: ctx.name || "",
				shown_error: ctx.error,
				error_action: ctx.action || "",
				new: 1,
			});
			genie.support_inbox.refresh_soon();
			// something else was opened meanwhile: the new chat waits in the list
			if (seq !== this.seq) return;
			this.render(r);
			if (this.opts.on_chat) this.opts.on_chat(r.conversation);
		} catch (e) {
			if (seq === this.seq) this.unavailable();
		}
	}

	// Send a form instead: the form starts with what is in the message box, and its ticket's chat opens.
	open_form() {
		const carried = this.tray.filter(
			(f) => !f.error && (f.kind === "image" || f.kind === "video")
		);
		const conversation = this.conversation; // the chat the form came from
		new genie.SupportTicket({
			prefill: {
				description: (this.input.value || "").trim(),
				files: carried,
				record: this.pending ? this.pending.record : null,
			},
			on_raised: (name) => {
				if (this.conversation === conversation) {
					this.input.value = "";
					this.tray = this.tray.filter((f) => !carried.includes(f));
					this.render_tray();
				} else {
					// the form was finished while another chat was open: only its own chat's draft lets go
					// of what went with it, and that other chat stays as it is
					const kept = this.drafts.get(conversation || null);
					if (kept) {
						kept.text = "";
						kept.tray = kept.tray.filter((f) => !carried.includes(f));
						if (!kept.tray.length) this.drafts.delete(conversation || null);
					}
				}
				genie.support_inbox
					.load()
					.catch(() => null)
					.then(() => {
						if (this.conversation === conversation) this.pick_ticket(name);
					});
			},
		});
	}
};

genie.format_bytes = function (bytes) {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

// One row of a list: the dot, the ticket's name and its one-line summary (and what is needed, when red).
genie.inbox_item = function (row, onclick, { need, active } = {}) {
	const b = document.createElement("button");
	b.type = "button";
	b.className = "genie-sc-item" + (active ? " active" : "");
	if (active) b.setAttribute("aria-current", "true");
	const text = document.createElement("span");
	text.className = "genie-sc-item-text";
	const sub = document.createElement("span");
	sub.className = "genie-sc-item-sub";
	if (row.dot) {
		const id = document.createElement("span");
		id.className = "genie-sc-item-id";
		id.textContent = row.name;
		sub.textContent = row.summary;
		text.append(id, sub);
	} else {
		const title = document.createElement("span");
		title.textContent = row.summary;
		sub.textContent = row.last_activity ? frappe.datetime.prettyDate(row.last_activity) : "";
		text.append(title, sub);
	}
	if (need && row.action) {
		const n = document.createElement("span");
		n.className = "genie-sc-item-need";
		n.textContent = row.action;
		text.appendChild(n);
	}
	b.append(genie.dot(row.dot), text);
	b.onclick = onclick;
	return b;
};
