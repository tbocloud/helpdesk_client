// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// The Support chat (TBO Copilot Phase 5): the Support button opens a chat with TBO
// Support's assistant. This site relays each message (helpdesk_client.chat); what TBO
// Support starts later (progress, the team's replies) arrives live over realtime.

frappe.provide("genie");

genie.SupportChat = class SupportChat {
	constructor() {
		if (genie.support_chat && document.body.contains(genie.support_chat.panel)) {
			genie.support_chat.show();
			return genie.support_chat;
		}
		genie.support_chat = this;
		this.context = genie.capture_context();
		this.conversation = null;
		this.busy = false;
		this.recording = null;
		this.build();
		this.listen();
		this.open(false);
	}

	call(method, args) {
		return frappe.xcall(`helpdesk_client.chat.${method}`, args);
	}

	build() {
		const panel = document.createElement("div");
		panel.id = "genie-support-chat";
		panel.className = "genie-no-record";
		panel.setAttribute("role", "dialog");
		panel.setAttribute("aria-label", __("Support chat"));
		Object.assign(panel.style, {
			position: "fixed",
			right: "24px",
			bottom: "90px",
			width: "380px",
			maxWidth: "calc(100vw - 32px)",
			height: "560px",
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
			<div class="genie-chat-head" style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--border-color,#e2e6e9)">
				<b style="flex:1">${__("TBO Support")}</b>
				<button type="button" class="btn btn-xs btn-default genie-chat-new">${__("New chat")}</button>
				<button type="button" class="btn btn-xs btn-default genie-chat-close" aria-label="${__("Close")}">×</button>
			</div>
			<div class="genie-chat-body" aria-live="polite" style="flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px"></div>
			<div class="genie-chat-recording" style="display:none;padding:6px 12px;background:var(--red-50,#fff0f0);font-size:12px"></div>
			<div class="genie-chat-foot" style="border-top:1px solid var(--border-color,#e2e6e9);padding:8px;display:flex;flex-direction:column;gap:6px">
				<textarea class="form-control genie-chat-input" rows="2" placeholder="${__("Write your message")}" aria-label="${__("Message")}" style="resize:none"></textarea>
				<div style="display:flex;gap:6px;align-items:center">
					<button type="button" class="btn btn-xs btn-default genie-chat-attach">${__("Attach")}</button>
					<button type="button" class="btn btn-xs btn-default genie-chat-record">${__("Record screen")}</button>
					<a href="#" class="genie-chat-form" style="font-size:12px;margin-left:auto">${__("Send a form instead")}</a>
					<button type="button" class="btn btn-xs btn-primary genie-chat-send">${__("Send")}</button>
				</div>
				<input type="file" class="genie-chat-file" accept="image/*,video/*,.pdf" style="display:none" multiple>
			</div>`;
		document.body.appendChild(panel);
		this.panel = panel;
		this.body = panel.querySelector(".genie-chat-body");
		this.input = panel.querySelector(".genie-chat-input");
		this.pill = panel.querySelector(".genie-chat-recording");
		panel.querySelector(".genie-chat-close").onclick = () => this.hide();
		panel.querySelector(".genie-chat-new").onclick = () => this.open(true);
		panel.querySelector(".genie-chat-send").onclick = () => this.send_text();
		panel.querySelector(".genie-chat-attach").onclick = () => panel.querySelector(".genie-chat-file").click();
		panel.querySelector(".genie-chat-file").onchange = (e) => this.attach(e.target.files);
		panel.querySelector(".genie-chat-record").onclick = () => this.toggle_recording();
		panel.querySelector(".genie-chat-form").onclick = (e) => {
			e.preventDefault();
			this.hide();
			new genie.SupportTicket();
		};
		this.input.addEventListener("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send_text();
			}
		});
	}

	listen() {
		frappe.realtime.on("helpdesk_client_chat", (data) => {
			if (data && data.conversation === this.conversation && data.message) {
				this.append(data.message);
			}
		});
	}

	show() {
		this.panel.style.display = "flex";
		this.input.focus();
	}

	hide() {
		this.panel.style.display = "none";
	}

	async open(fresh) {
		this.body.innerHTML = "";
		this.typing(true);
		try {
			const r = await this.call("start", { ...this.context, new: fresh ? 1 : 0 });
			this.conversation = r.conversation;
			this.body.innerHTML = "";
			(r.messages || []).forEach((m) => this.append(m));
		} catch (e) {
			this.unavailable();
		} finally {
			this.typing(false);
			this.input.focus();
		}
	}

	unavailable() {
		this.body.innerHTML = "";
		const div = document.createElement("div");
		div.style.cssText = "padding:12px;font-size:13px";
		div.innerHTML = `<p>${__("The support chat is not available right now.")}</p>`;
		const button = document.createElement("button");
		button.className = "btn btn-sm btn-primary";
		button.textContent = __("Send a form instead");
		button.onclick = () => {
			this.hide();
			new genie.SupportTicket();
		};
		div.appendChild(button);
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
		wrap.style.cssText = `display:flex;flex-direction:column;align-items:${mine ? "flex-end" : "flex-start"}`;
		const bubble = document.createElement("div");
		bubble.style.cssText = `max-width:85%;padding:8px 10px;border-radius:10px;font-size:13px;white-space:pre-wrap;word-wrap:break-word;${
			mine
				? "background:var(--blue-100,#e6f0ff)"
				: message.kind === "Stage"
				? "background:var(--yellow-50,#fffbea);border:1px solid var(--yellow-200,#fbe7a3)"
				: "background:var(--subtle-fg,#f4f5f6)"
		}`;
		const card = message.card || {};
		if (card.title) {
			const title = document.createElement("div");
			title.style.fontWeight = "600";
			title.textContent = card.title;
			bubble.appendChild(title);
		}
		const lines = card.lines && card.lines.length ? card.lines : message.text ? [message.text] : [];
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
		if (card.actions && card.actions.length) {
			const row = document.createElement("div");
			row.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin-top:6px";
			card.actions.forEach((a) => {
				const b = document.createElement("button");
				b.type = "button";
				b.className = `btn btn-xs ${a.style === "positive" ? "btn-primary" : "btn-default"}`;
				b.textContent = a.label;
				b.onclick = () => {
					row.querySelectorAll("button").forEach((x) => (x.disabled = true));
					this.act(a.verb);
				};
				row.appendChild(b);
			});
			wrap.appendChild(row);
		}
		const typing = this.body.querySelector(".genie-chat-typing");
		this.body.insertBefore(wrap, typing || null);
		this.scroll();
	}

	async post(args) {
		if (!this.conversation || this.busy) return;
		this.busy = true;
		this.typing(true);
		try {
			const r = await this.call("send", { conversation: this.conversation, ...args });
			(r.messages || []).forEach((m) => this.append(m));
		} catch (e) {
			this.append({ direction: "System", kind: "Text", text: __("That did not reach TBO Support. Try again, or send a form instead.") });
		} finally {
			this.busy = false;
			this.typing(false);
		}
	}

	send_text() {
		const text = (this.input.value || "").trim();
		if (!text) return;
		this.input.value = "";
		this.append({ direction: "Customer", kind: "Text", text });
		this.post({ text });
	}

	act(verb) {
		if (verb === "record") return this.toggle_recording();
		if (verb === "still_broken") {
			frappe.prompt(
				{ fieldname: "note", fieldtype: "Small Text", label: __("What is still wrong?"), reqd: 1 },
				(v) => this.post({ action: "still_broken", note: v.note }),
				__("Still broken"),
				__("Send")
			);
			return;
		}
		this.post({ action: verb });
	}

	async attach(fileList) {
		const files = [];
		for (const file of Array.from(fileList || []).slice(0, 5)) {
			const url = await genie.UploadFile(file, file.name, { is_private: 1 }).catch(() => null);
			if (url) files.push({ file_url: url, file_name: file.name });
		}
		this.panel.querySelector(".genie-chat-file").value = "";
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
			frappe.msgprint(__("This browser cannot record the screen; you can attach a screenshot instead."));
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
			label.textContent = `⏺ ${__("Recording")} ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} `;
			const stop = document.createElement("button");
			stop.type = "button";
			stop.className = "btn btn-xs btn-default";
			stop.textContent = __("Stop");
			stop.onclick = () => recorder.stop();
			this.pill.append(label, stop);
		}, 500);
		this.pill.style.display = "block";
		stream.getVideoTracks()[0].addEventListener("ended", () => recorder.state === "recording" && recorder.stop());
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
