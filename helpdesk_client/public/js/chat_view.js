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
			});
		return this.loading;
	},
	refresh_soon() {
		clearTimeout(this.timer);
		this.timer = setTimeout(() => this.load().catch(() => null), 500);
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
		this.recording = null;
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
			<div class="genie-sc-recording" style="display:none;padding:6px 12px;background:var(--red-50,#fff0f0);font-size:12px"></div>
			<div class="genie-sc-foot" hidden>
				<textarea class="form-control genie-sc-input" rows="2" placeholder="${__(
					"Write your message"
				)}" aria-label="${__(
			"Message"
		)}" style="resize:none;height:60px;min-height:60px"></textarea>
				<div class="genie-sc-tools">
					<button type="button" class="btn btn-xs btn-default genie-sc-attach">${__("Attach")}</button>
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
		this.pill = el.querySelector(".genie-sc-recording");
		this.foot = el.querySelector(".genie-sc-foot");
		this.closed = el.querySelector(".genie-sc-closed");
		this.input = el.querySelector(".genie-sc-input");
		this.file = el.querySelector(".genie-sc-file");
		el.querySelector(".genie-sc-send").onclick = () => this.send_text();
		el.querySelector(".genie-sc-attach").onclick = () => this.file.click();
		this.file.onchange = (e) => this.attach(e.target.files);
		el.querySelector(".genie-sc-record").onclick = () => this.toggle_recording();
		el.querySelector(".genie-sc-form").onclick = (e) => {
			e.preventDefault();
			new genie.SupportTicket();
		};
		this.input.addEventListener("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send_text();
			}
		});
	}

	call(method, args) {
		return frappe.xcall(`helpdesk_client.${method}`, args);
	}

	// --- what the view shows ----------------------------------------------------------------------

	waiting() {
		this.conversation = null;
		this.ticket = null;
		this.body.innerHTML = "";
		this.head.hidden = this.status.hidden = this.foot.hidden = this.closed.hidden = true;
		this.typing(true);
	}

	async open_ticket(name) {
		this.waiting();
		try {
			this.render(await this.call("chat.open_ticket", { ticket: name }));
		} catch (e) {
			this.unavailable();
		}
	}

	async open_chat(name) {
		this.waiting();
		try {
			this.render(await this.call("chat.history", { conversation: name }));
		} catch (e) {
			this.unavailable();
		}
	}

	// A new chat checks first that it is a new problem, not one of the user's open tickets.
	async start_new(checked) {
		if (!checked) {
			this.waiting();
			const data = await genie.support_inbox.load().catch(() => null);
			const open = data ? data.tickets.filter((t) => !t.closed) : [];
			if (open.length) return this.ask_new_or_ticket(open);
		}
		this.waiting();
		try {
			const r = await this.call("chat.start", { ...genie.capture_context(), new: 1 });
			this.render(r);
			if (this.opts.on_chat) this.opts.on_chat(r.conversation);
			genie.support_inbox.refresh_soon();
		} catch (e) {
			this.unavailable();
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
		this.body.innerHTML = "";
		(r.messages || []).forEach((m) => this.append(m));
		if (r.note) this.append({ direction: "System", kind: "Text", text: r.note });
		this.render_head();
		this.render_status();
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
		this.status.append(
			this.button(__("What's the status?"), "btn-default", () => this.ask_status())
		);
	}

	render_foot(read_only) {
		const closed = !!(this.ticket && this.ticket.closed);
		this.foot.hidden = read_only || closed || !this.conversation;
		this.closed.innerHTML = "";
		this.closed.hidden = !closed;
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
			this.button(__("Send a form instead"), "btn-primary", () => new genie.SupportTicket())
		);
		this.body.appendChild(div);
	}

	typing(on) {
		let dot = this.body.querySelector(".genie-chat-typing");
		if (on && !dot) {
			dot = document.createElement("div");
			dot.className = "genie-chat-typing text-muted";
			dot.style.fontSize = "12px";
			dot.textContent = __("TBO Support is writing…");
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
			actions.forEach((a) => {
				const b = this.button(
					a.label,
					a.style === "positive" ? "btn-primary" : "btn-default",
					() => {
						row.querySelectorAll("button").forEach((x) => (x.disabled = true));
						this.act(a.verb);
					}
				);
				row.appendChild(b);
			});
			wrap.appendChild(row);
		}
		const typing = this.body.querySelector(".genie-chat-typing");
		this.body.insertBefore(wrap, typing || null);
		this.scroll();
	}

	// --- what the user does -----------------------------------------------------------------------

	async post(args) {
		if (!this.conversation || this.busy) return;
		this.busy = true;
		this.typing(true);
		let r = null;
		try {
			r = await this.call("chat.send", { conversation: this.conversation, ...args });
			(r.messages || []).forEach((m) => this.append(m));
		} catch (e) {
			this.append({
				direction: "System",
				kind: "Text",
				text: __("That did not reach TBO Support. Try again, or send a form instead."),
			});
		} finally {
			this.busy = false;
			this.typing(false);
		}
		if (!r) return;
		genie.support_inbox.refresh_soon();
		if (r.ticket && !this.ticket) {
			// the chat became a ticket: from now on it is shown under the ticket's name
			if (this.opts.on_ticket) this.opts.on_ticket(r.ticket);
			else this.open_ticket(r.ticket);
		} else if (this.ticket && ["fixed", "still_broken"].includes(args.action)) {
			this.open_ticket(this.ticket.name);
		}
	}

	send_text() {
		const text = (this.input.value || "").trim();
		if (!text || !this.conversation) return;
		this.input.value = "";
		this.append({ direction: "Customer", kind: "Text", text });
		this.post({ text });
	}

	act(verb) {
		if (verb === "record") return this.toggle_recording();
		if (verb === "fixed") return this.answer_fix(true);
		if (verb === "still_broken") return this.answer_fix(false);
		this.post({ action: verb });
	}

	// It's fixed / Still broken / It came back: recorded on the ticket, so its dot changes at once.
	answer_fix(fixed, question) {
		const go = (note) => {
			if (this.conversation)
				return this.post({ action: fixed ? "fixed" : "still_broken", note });
			const method = fixed ? "confirm_resolution" : "reopen";
			return frappe
				.xcall(
					`helpdesk_client.helpdesk_client.doctype.support_ticket.support_ticket.${method}`,
					{
						ticket: this.ticket.name,
						note,
					}
				)
				.then(() => {
					genie.support_inbox.refresh_soon();
					this.open_ticket(this.ticket.name);
				});
		};
		if (fixed) return go("");
		frappe.prompt(
			{
				fieldname: "note",
				fieldtype: "Small Text",
				label: question || __("What is still wrong?"),
				reqd: 1,
			},
			(v) => go(v.note),
			__("Tell TBO Support"),
			__("Send")
		);
	}

	async ask_status() {
		if (!this.ticket) return;
		try {
			this.append(await this.call("inbox.ticket_status", { ticket: this.ticket.name }));
		} catch (e) {
			this.append({
				direction: "System",
				kind: "Text",
				text: __("The status could not be read just now."),
			});
		}
	}

	async attach(fileList) {
		const files = [];
		for (const file of Array.from(fileList || []).slice(0, 5)) {
			const url = await genie
				.UploadFile(file, file.name, { is_private: 1 })
				.catch(() => null);
			if (url) files.push({ file_url: url, file_name: file.name });
		}
		this.file.value = "";
		if (!files.length) return;
		this.append({ direction: "Customer", kind: "Text", text: "", files });
		this.post({ files: JSON.stringify(files) });
	}

	cap_bytes() {
		// the site's own upload limit wins over the recording setting (Frappe's default is 25 MB)
		const setting = (frappe.boot.genie_max_file_size || 25) * 1024 * 1024;
		const site = frappe.boot.max_file_size || 25 * 1024 * 1024;
		return Math.min(setting, site);
	}

	async toggle_recording() {
		if (this.recording) return this.recording.recorder.stop();
		if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
			frappe.msgprint(
				__("This browser cannot record the screen; you can attach a screenshot instead.")
			);
			return;
		}
		let stream;
		try {
			stream = await navigator.mediaDevices.getDisplayMedia(genie.display_media_options());
		} catch (e) {
			return; // the user said no in the browser's own prompt
		}
		const recorder = genie.make_media_recorder(stream);
		const chunks = [];
		let size = 0;
		const started = Date.now();
		this.recording = { recorder, stream };
		recorder.ondataavailable = (e) => {
			if (!e.data || !e.data.size) return;
			chunks.push(e.data);
			size += e.data.size;
			if (size >= this.cap_bytes() && recorder.state === "recording") recorder.stop();
		};
		const tick = setInterval(() => {
			const s = Math.round((Date.now() - started) / 1000);
			this.pill.innerHTML = "";
			const label = document.createElement("span");
			label.textContent = `⏺ ${__("Recording")} ${Math.floor(s / 60)}:${String(
				s % 60
			).padStart(2, "0")} `;
			this.pill.append(
				label,
				this.button(__("Stop"), "btn-default", () => recorder.stop())
			);
		}, 500);
		this.pill.style.display = "block";
		stream
			.getVideoTracks()[0]
			.addEventListener("ended", () => recorder.state === "recording" && recorder.stop());
		recorder.onstop = async () => {
			clearInterval(tick);
			stream.getTracks().forEach((t) => t.stop());
			this.pill.style.display = "none";
			this.recording = null;
			const type = recorder.mimeType || "video/webm";
			const blob = new Blob(chunks, { type });
			const name = `screen-recording-${Date.now()}.${type.includes("mp4") ? "mp4" : "webm"}`;
			const url = await genie.UploadFile(blob, name, { is_private: 1 }).catch(() => null);
			if (!url) return;
			const files = [{ file_url: url, file_name: name }];
			this.append({ direction: "Customer", kind: "Text", text: "", files });
			this.post({ action: "recorded", files: JSON.stringify(files) });
		};
		recorder.start(1000);
	}
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
