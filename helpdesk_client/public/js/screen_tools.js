// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

// Screenshots and screen recordings for the support chat (TBO Copilot Phase 14). A recording keeps going
// while the panel is closed: a bar floats at the bottom of the screen with the time, the voice, Discard
// and Stop and attach. It stops by itself at the site's time and size limits, and when the user ends
// sharing in the browser's own bar.

frappe.provide("genie");

// Screen readers hear what happens (recording started, attached, a reply arrived) from one live region.
genie.announce = function (text) {
	let region = document.getElementById("genie-live");
	if (!region) {
		region = document.createElement("div");
		region.id = "genie-live";
		region.setAttribute("aria-live", "polite");
		region.style.cssText =
			"position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap";
		document.body.appendChild(region);
	}
	region.textContent = "";
	setTimeout(() => (region.textContent = text || ""), 50);
};

genie.can_record_screen = function () {
	// phone browsers cannot share their screen
	return !!(
		navigator.mediaDevices &&
		navigator.mediaDevices.getDisplayMedia &&
		window.MediaRecorder &&
		!frappe.is_mobile()
	);
};

// What a recording is and who can watch it (Phase 23 B11), said before it starts, in the chat and the form.
genie.recording_note = function () {
	return __(
		"You choose in your browser's prompt what to share: this tab, a window or your whole screen. The recording is attached privately to your ticket: TBO Support's team can watch it, and so can people on this site who can open the ticket (colleagues who follow it, and your System Managers). Your voice is recorded only if you choose it."
	);
};

// Before a recording from the chat: the note, and the voice (off unless chosen). {voice} or null when cancelled.
genie.recording_choice = function () {
	return new Promise((resolve) => {
		let chosen = null;
		const d = new frappe.ui.Dialog({
			title: __("Record your screen"),
			fields: [
				{ fieldtype: "HTML", fieldname: "note" },
				{
					fieldtype: "Check",
					fieldname: "voice",
					label: __("Also record my voice (microphone)"),
					default: 0,
				},
			],
			primary_action_label: __("Start recording"),
			primary_action: (values) => {
				chosen = { voice: !!values.voice };
				d.hide();
			},
		});
		const p = document.createElement("p");
		p.className = "text-muted";
		p.textContent = genie.recording_note();
		d.fields_dict.note.$wrapper.empty().append(p);
		d.onhide = () => resolve(chosen);
		d.show();
	});
};

genie.format_seconds = function (seconds) {
	const s = Math.max(0, Math.floor(seconds || 0));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

// One still frame of the shared tab, as a PNG; null when the user says no.
genie.capture_screenshot = async function () {
	if (!genie.can_record_screen()) {
		frappe.msgprint(__("This browser cannot capture the screen; attach an image instead."));
		return null;
	}
	let stream;
	try {
		stream = await navigator.mediaDevices.getDisplayMedia(genie.display_media_options());
	} catch (e) {
		return null; // the user said no in the browser's own prompt
	}
	try {
		const video = document.createElement("video");
		video.muted = true;
		video.srcObject = stream;
		await video.play();
		await new Promise((resolve) => requestAnimationFrame(() => resolve()));
		const canvas = document.createElement("canvas");
		canvas.width = video.videoWidth;
		canvas.height = video.videoHeight;
		canvas.getContext("2d").drawImage(video, 0, 0);
		return await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
	} finally {
		stream.getTracks().forEach((t) => t.stop());
	}
};

genie.screen_recorder = {
	session: null,
	listeners: [],

	on_change(fn) {
		this.listeners.push(fn);
	},

	changed() {
		this.listeners.forEach((fn) => fn(!!this.session));
	},

	recording() {
		return !!this.session;
	},

	cap_seconds() {
		return frappe.boot.genie_recording_seconds || 180;
	},

	cap_bytes() {
		// the site's own upload limit wins over the recording setting (Frappe's default is 25 MB)
		const setting = (frappe.boot.genie_max_file_size || 25) * 1024 * 1024;
		const site = frappe.boot.max_file_size || 25 * 1024 * 1024;
		return Math.min(setting, site);
	},

	// on_done({blob, name, kind, size, seconds}) once the user stops (not when they discard); the voice only
	// with {voice: true}. True when the recording started; false when it could not (no screen capture, or the
	// user said no).
	async start(on_done, opts) {
		// one recording at a time, also while the browser still asks what to share
		if (this.session || this.starting) return false;
		this.starting = true;
		try {
			return await this.begin(on_done, opts);
		} finally {
			this.starting = false;
		}
	},

	async begin(on_done, { voice: with_voice = false } = {}) {
		if (!genie.can_record_screen()) {
			frappe.msgprint(
				__("This browser cannot record the screen; you can attach a screenshot instead.")
			);
			return false;
		}
		let display;
		try {
			display = await navigator.mediaDevices.getDisplayMedia(genie.display_media_options());
		} catch (e) {
			return false; // the user said no in the browser's own prompt
		}
		// the voice only when the user chose it; without a microphone the screen is still recorded
		let voice = null;
		if (with_voice) {
			try {
				voice = await navigator.mediaDevices.getUserMedia({
					audio: { echoCancellation: true, noiseSuppression: true },
				});
			} catch (e) {
				voice = null;
			}
		}
		const stream = new MediaStream([
			...display.getVideoTracks(),
			...(voice ? voice.getAudioTracks() : []),
		]);
		// the browser would not record this stream: nothing stays shared, and the user is told
		const fail = () => {
			[display, voice].forEach((st) => st && st.getTracks().forEach((t) => t.stop()));
			frappe.msgprint(
				__("This browser cannot record the screen; you can attach a screenshot instead.")
			);
			return false;
		};
		let recorder;
		try {
			recorder = genie.make_media_recorder(stream);
		} catch (e) {
			return fail();
		}
		const s = {
			recorder,
			display,
			voice,
			asked_voice: with_voice,
			chunks: [],
			size: 0,
			biggest: 0,
			started: Date.now(),
			on_done,
		};
		this.session = s;
		recorder.ondataavailable = (e) => {
			if (!e.data || !e.data.size) return;
			s.chunks.push(e.data);
			s.size += e.data.size;
			s.biggest = Math.max(s.biggest, e.data.size);
			// stopped early enough that what stopping still hands over fits the upload limit
			if (s.size + 2 * s.biggest >= this.cap_bytes()) this.stop();
		};
		recorder.onstop = () => this.finish(s);
		display.getVideoTracks()[0].addEventListener("ended", () => this.stop());
		try {
			recorder.start(1000);
		} catch (e) {
			this.session = null;
			return fail();
		}
		this.show_bar();
		this.tick = setInterval(() => this.update_bar(), 500);
		this.changed();
		genie.announce(__("Recording the screen. Show the problem, then press Stop and attach."));
		return true;
	},

	stop(discard = false) {
		const s = this.session;
		if (!s || s.stopping) return;
		s.stopping = true;
		s.discard = discard;
		s.seconds = (Date.now() - s.started) / 1000;
		if (s.recorder.state !== "inactive") s.recorder.stop();
		else this.finish(s);
	},

	finish(s) {
		if (this.session !== s) return;
		this.session = null;
		clearInterval(this.tick);
		[s.display, s.voice].forEach((st) => st && st.getTracks().forEach((t) => t.stop()));
		this.hide_bar();
		this.changed();
		if (s.discard) {
			genie.announce(__("Recording discarded."));
			return;
		}
		const type = (s.recorder.mimeType || "video/webm").split(";")[0];
		const blob = new Blob(s.chunks, { type });
		if (!blob.size) {
			frappe.show_alert({
				indicator: "orange",
				message: __("The recording came out empty. Try again."),
			});
			return;
		}
		// over the upload limit all the same: it could not be attached
		if (blob.size > this.cap_bytes()) {
			frappe.show_alert({
				indicator: "orange",
				message: __("The recording came out larger than {0}. Record a shorter one.", [
					genie.format_bytes(this.cap_bytes()),
				]),
			});
			return;
		}
		const name = `screen-recording-${Date.now()}.${type.includes("mp4") ? "mp4" : "webm"}`;
		genie.announce(__("Recording attached."));
		if (s.on_done) {
			s.on_done({
				blob,
				name,
				kind: "video",
				size: blob.size,
				seconds: Math.round(s.seconds || 0),
			});
		}
	},

	toggle_voice() {
		const s = this.session;
		const tracks = s && s.voice ? s.voice.getAudioTracks() : [];
		if (!tracks.length) return;
		const on = !tracks[0].enabled;
		tracks.forEach((t) => (t.enabled = on));
		this.update_bar();
	},

	show_bar() {
		genie.support_css();
		let bar = document.getElementById("genie-recording-bar");
		if (!bar) {
			bar = document.createElement("section");
			bar.id = "genie-recording-bar";
			bar.className = "genie-no-record";
			bar.setAttribute("aria-label", __("Screen recording"));
			bar.innerHTML = `
				<div class="genie-rb-row">
					<span class="genie-rb-dot" aria-hidden="true"></span>
					<b>${__("Recording")}</b>
					<span class="genie-rb-time"></span>
					<span class="genie-rb-buttons">
						<button type="button" class="btn btn-xs btn-default genie-rb-voice"></button>
						<button type="button" class="btn btn-xs btn-default genie-rb-discard">${__("Discard")}</button>
						<button type="button" class="btn btn-xs btn-danger genie-rb-stop">■ ${__(
							"Stop and attach"
						)}</button>
					</span>
				</div>
				<div class="genie-rb-hint">${__(
					"Show the problem, then press Stop. The panel can stay closed meanwhile."
				)}</div>`;
			document.body.appendChild(bar);
			bar.querySelector(".genie-rb-voice").onclick = () => this.toggle_voice();
			bar.querySelector(".genie-rb-discard").onclick = () => this.stop(true);
			bar.querySelector(".genie-rb-stop").onclick = () => this.stop();
		}
		bar.hidden = false;
		this.update_bar();
	},

	update_bar() {
		const bar = document.getElementById("genie-recording-bar");
		const s = this.session;
		if (!bar || !s) return;
		const elapsed = (Date.now() - s.started) / 1000;
		const cap = this.cap_seconds();
		if (elapsed >= cap) return this.stop();
		const left = cap - elapsed;
		const time = bar.querySelector(".genie-rb-time");
		time.textContent =
			left <= 20
				? __("{0} left", [genie.format_seconds(left)])
				: `${genie.format_seconds(elapsed)} / ${genie.format_seconds(cap)}`;
		time.classList.toggle("genie-rb-ending", left <= 20);
		const voice = bar.querySelector(".genie-rb-voice");
		const tracks = s.voice ? s.voice.getAudioTracks() : [];
		if (!tracks.length) {
			// not chosen before the start, or no microphone: either way no voice in this recording
			voice.textContent = s.asked_voice
				? __("No microphone")
				: "🔇 " + __("Voice not recorded");
			voice.disabled = true;
			voice.removeAttribute("aria-pressed");
		} else {
			const on = tracks[0].enabled;
			voice.disabled = false;
			voice.textContent = on ? "🎤 " + __("Voice on") : "🔇 " + __("Voice off");
			voice.setAttribute("aria-pressed", on ? "true" : "false");
			voice.title = on ? __("Mute my voice") : __("Record my voice");
		}
	},

	hide_bar() {
		const bar = document.getElementById("genie-recording-bar");
		if (bar) bar.hidden = true;
	},
};
