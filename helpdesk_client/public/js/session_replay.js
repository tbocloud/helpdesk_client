// Copyright (c) 2026, Quark Cyber Systems FZC and Contributors
// MIT License. See license.txt
//
// Session replay: keeps the last few minutes of desk activity (rrweb) in
// memory so a ticket can show support what happened. Nothing is stored or
// sent until the user raises a ticket with "Attach what I did" ticked.
// The hub reads the files built here — keep their shape in step with it.

frappe.provide("genie");

const RRWEB_PATH = "/assets/helpdesk_client/js/lib/rrweb/";
const SEGMENT_MS = 60 * 1000;
// A busy page can emit thousands of mutations a minute; starting a new
// segment early keeps what the trimmed buffer holds bounded.
const MAX_SEGMENT_EVENTS = 20000;
const MAX_ERRORS = 5;
const MAX_TEXT = 500;
const RECENT_ERRORS = 20;
const HIDE_ALL_TEXT = "Hide all text";
const EVENT_META = 4;
const EVENT_PLUGIN = 6;
const CONSOLE_PLUGIN = "rrweb/console@1";
const EMAIL_RE = /[^\s@]+@[^\s@]+\.[^\s@]+/g;

// Blocked elements replay as blank boxes of the same size.
const BLOCK_SELECTOR = [
	"img",
	"video",
	"canvas",
	"iframe",
	"object",
	"embed",
	".form-attachments",
	".attachment-row",
	".attachment-gallery-item",
	".file-uploader",
	".file-preview",
	".file-preview-area",
	".preview-image",
	".image-view-body",
	".genie-no-record",
].join(", ");

genie.SessionReplay = class SessionReplay {
	constructor(config) {
		this.minutes = cint(config.minutes) || 2;
		this.privacy = config.privacy || "Hide numbers and typed values";
		this.segments = [];
		this.recent_errors = [];
		this.error_count = 0;
		this.active = false;
		this.stop_recording = null;
		this.checkout_pending = false;
	}

	async start() {
		// Without gzip the file cannot be built, so don't record at all.
		if (!window.CompressionStream) return;

		await load_script("record.min.js");
		const rrweb = window.rrwebRecord;
		if (!rrweb || typeof rrweb.record !== "function") return;
		this.record = rrweb.record;

		const plugins = await this.load_plugins();
		this.stop_recording = this.record({
			emit: (event, is_checkout) => this.on_event(event, is_checkout),
			checkoutEveryNms: SEGMENT_MS,
			plugins,
			maskAllInputs: true,
			maskTextSelector: "*",
			maskTextFn: (text) => this.mask_text(text),
			blockSelector: BLOCK_SELECTOR,
			slimDOMOptions: "all",
			sampling: { mousemove: 250, mousemoveCallback: 1000, scroll: 150, input: "last" },
			recordCanvas: false,
			collectFonts: false,
			inlineImages: false,
			errorHandler: (err) => {
				this.on_error(err);
				return true;
			},
		});
		// record() swallows its own start-up failures and returns nothing.
		if (typeof this.stop_recording !== "function") return;

		this.active = true;
		this.watch_desk();
	}

	async load_plugins() {
		const plugins = [];
		const [console_lib, network_lib] = await Promise.allSettled([
			load_script("rrweb-plugin-console-record.min.js"),
			load_script("rrweb-plugin-network-record.min.js"),
		]);

		const console_plugin = window.rrwebPluginConsoleRecord;
		if (console_lib.status === "fulfilled" && console_plugin) {
			plugins.push(
				console_plugin.getRecordConsolePlugin({
					level: ["warn", "error"],
					lengthThreshold: 200,
					stringifyOptions: {
						stringLengthLimit: MAX_TEXT,
						numOfKeysLimit: 20,
						depthOfLimit: 2,
					},
				})
			);
		}

		const network_plugin = window.rrwebPluginNetworkRecord;
		if (network_lib.status === "fulfilled" && network_plugin) {
			plugins.push(
				network_plugin.getRecordNetworkPlugin({
					// Timing and status only; headers and bodies may hold data.
					initiatorTypes: ["fetch", "xmlhttprequest", "navigation"],
					recordHeaders: false,
					recordBody: false,
					recordInitialRequests: false,
					transformRequestFn: (request) => this.clean_request(request),
				})
			);
		}
		return plugins;
	}

	stop() {
		this.active = false;
		this.segments = [];
		try {
			this.stop_recording && this.stop_recording();
		} catch (err) {
			// already torn down
		}
		this.stop_recording = null;
	}

	is_ready() {
		return this.active && this.segments.length > 0;
	}

	safely(fn) {
		if (!this.active) return;
		try {
			fn();
		} catch (err) {
			this.on_error(err);
		}
	}

	on_error() {
		this.error_count += 1;
		if (this.error_count >= MAX_ERRORS) this.stop();
	}

	on_event(event, is_checkout) {
		try {
			if (event.type === EVENT_META && (is_checkout || !this.segments.length)) {
				this.segments.push([]);
				this.checkout_pending = false;
				while (this.segments.length > this.minutes + 1) this.segments.shift();
				// Once the full snapshot is in, so every kept segment says where it is.
				setTimeout(() => this.safely(() => this.note_route()), 0);
			}
			const segment = this.segments[this.segments.length - 1];
			if (!segment) return;
			if (event.type === EVENT_PLUGIN) this.on_plugin_event(event);
			segment.push(event);

			if (segment.length > MAX_SEGMENT_EVENTS && !this.checkout_pending) {
				this.checkout_pending = true;
				setTimeout(() => this.safely(() => this.record.takeFullSnapshot(true)), 0);
			}
		} catch (err) {
			this.on_error(err);
		}
	}

	on_plugin_event(event) {
		const data = event.data || {};
		if (data.plugin !== CONSOLE_PLUGIN || !data.payload) return;
		// The console can print anything; hold it to the same privacy promise.
		const log = data.payload;
		log.payload = (log.payload || []).map((part) => clip(this.mask_text(String(part))));
		if (log.level === "error") this.note_error("console", log.payload.join(" "));
	}

	add_event(tag, payload) {
		if (!this.is_ready()) return;
		this.record.addCustomEvent(tag, payload);
	}

	note_error(kind, message, extra = {}) {
		this.recent_errors.push(
			Object.assign({ time: Date.now(), kind, message: clip(message) }, extra)
		);
		if (this.recent_errors.length > RECENT_ERRORS) this.recent_errors.shift();
	}

	watch_desk() {
		frappe.router.on("change", () => this.safely(() => this.note_route()));
		this.wrap_msgprint();
		$(document).ajaxComplete((e, xhr, settings) =>
			this.safely(() => this.on_ajax_complete(xhr, settings))
		);
	}

	note_route() {
		this.add_event("frappe-route", {
			route: frappe.get_route(),
			url: window.location.pathname,
		});
	}

	wrap_msgprint() {
		const original = frappe.msgprint;
		const replay = this;
		frappe.msgprint = function (...args) {
			replay.safely(() => replay.on_msgprint(args[0], args[1]));
			return original.apply(this, args);
		};
	}

	on_msgprint(msg, title) {
		// An array is re-dispatched item by item through frappe.msgprint.
		if (!msg || Array.isArray(msg)) return;
		let data = msg;
		if (typeof msg === "string" && msg.startsWith("{")) {
			try {
				data = JSON.parse(msg);
			} catch (err) {
				data = { message: msg };
			}
		} else if (!$.isPlainObject(msg)) {
			data = { message: msg, title };
		}
		let message = data.message;
		if (Array.isArray(message)) message = message.flat().join(" ");
		if (!message) return;

		const payload = {
			title: this.clean_text(data.title || title || ""),
			message: this.clean_text(message),
		};
		this.add_event("frappe-msgprint", payload);
		if (data.raise_exception || ["red", "orange"].includes(data.indicator)) {
			this.note_error("msgprint", payload.message);
		}
	}

	on_ajax_complete(xhr, settings) {
		if (!xhr || xhr.status < 400) return;
		const url = String((settings && settings.url) || "");
		const match = url.match(/\/api\/(?:v\d+\/)?method\/([^?#]+)/);
		const method = match ? decodeURIComponent(match[1]) : url.split(/[?#]/)[0];

		let r = xhr.responseJSON;
		if (!r && xhr.responseText) {
			try {
				r = JSON.parse(xhr.responseText);
			} catch (err) {
				r = null;
			}
		}
		r = r && typeof r === "object" ? r : {};

		const payload = {
			method,
			status: xhr.status,
			exc_type: r.exc_type || "",
			message: this.clean_text(server_message(r) || xhr.statusText || ""),
		};
		this.add_event("frappe-call-error", payload);
		const extra = { method, status: xhr.status };
		if (payload.exc_type) extra.exc_type = payload.exc_type;
		this.note_error("call", payload.message, extra);
	}

	clean_request(request) {
		const name = String(request.name || "");
		if (name.includes("/api/method/upload_file") || name.includes("/socket.io/")) {
			return null;
		}
		return Object.assign({}, request, { name: name.split(/[?#]/)[0] });
	}

	mask_text(text) {
		if (!text) return text;
		if (this.privacy === HIDE_ALL_TEXT) return text.replace(/[\p{L}\p{N}]/gu, "•");
		return text.replace(EMAIL_RE, "•••@•••").replace(/\p{Nd}/gu, "•");
	}

	clean_text(value) {
		let text = value == null ? "" : String(value);
		if (/[<&]/.test(text)) {
			// DOMParser documents are inert: no scripts run, no images load.
			text = new DOMParser().parseFromString(text, "text/html").body.textContent || "";
		}
		return clip(this.mask_text(text.replace(/\s+/g, " ").trim()));
	}

	async build_files() {
		if (!this.is_ready()) return null;
		this.add_event("raise-ticket", {});

		const events = [].concat(...this.segments);
		const replay = {
			version: 1,
			minutes: this.minutes,
			privacy: this.privacy,
			started_at: events[0].timestamp,
			ended_at: events[events.length - 1].timestamp,
			events,
		};
		return {
			replay: await gzip(JSON.stringify(replay)),
			diagnostics: new Blob([JSON.stringify(this.diagnostics())], {
				type: "application/json",
			}),
		};
	}

	diagnostics() {
		const ua = navigator.userAgent || "";
		let timezone = "";
		try {
			timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
		} catch (err) {
			// very old browser
		}
		return {
			version: 1,
			captured_at: new Date().toISOString(),
			url: window.location.origin + window.location.pathname,
			route: frappe.get_route(),
			title: document.title,
			user_agent: ua,
			browser: detect_browser(ua),
			os: detect_os(ua),
			viewport: { w: window.innerWidth, h: window.innerHeight },
			screen: { w: window.screen.width, h: window.screen.height },
			timezone,
			language: navigator.language || "",
			versions: frappe.boot.versions || {},
			site: frappe.boot.sitename || window.location.host,
			recent_errors: this.recent_errors.slice(-RECENT_ERRORS),
		};
	}
};

function load_script(file) {
	return new Promise((resolve, reject) => {
		const script = document.createElement("script");
		const version = encodeURIComponent(window._version_number || "");
		script.src = `${RRWEB_PATH}${file}?v=${version}`;
		script.async = true;
		script.onload = resolve;
		script.onerror = reject;
		document.head.appendChild(script);
	});
}

async function gzip(text) {
	const stream = new Blob([text]).stream().pipeThrough(new window.CompressionStream("gzip"));
	const blob = await new Response(stream).blob();
	return new Blob([blob], { type: "application/gzip" });
}

function clip(text) {
	text = text == null ? "" : String(text);
	return text.length > MAX_TEXT ? `${text.slice(0, MAX_TEXT - 1)}…` : text;
}

function server_message(r) {
	if (r._server_messages) {
		try {
			return JSON.parse(r._server_messages)
				.map((m) => {
					const parsed = typeof m === "string" ? JSON.parse(m) : m;
					return (parsed && parsed.message) || "";
				})
				.filter(Boolean)
				.join(" | ");
		} catch (err) {
			// fall through to the exception line
		}
	}
	if (typeof r.exception === "string") return r.exception;
	return typeof r.message === "string" ? r.message : "";
}

function detect_browser(ua) {
	const rules = [
		["Edge", /Edg(?:e|A|iOS)?\/([\d.]+)/],
		["Opera", /OPR\/([\d.]+)/],
		["Samsung Internet", /SamsungBrowser\/([\d.]+)/],
		["Chrome", /(?:Chrome|CriOS)\/([\d.]+)/],
		["Firefox", /(?:Firefox|FxiOS)\/([\d.]+)/],
		["Safari", /Version\/([\d.]+).*Safari/],
	];
	for (const [name, re] of rules) {
		const m = ua.match(re);
		if (m) return `${name} ${m[1]}`;
	}
	return "";
}

function detect_os(ua) {
	const windows = ua.match(/Windows NT ([\d.]+)/);
	if (windows) {
		const names = { "10.0": "10/11", 6.3: "8.1", 6.2: "8", 6.1: "7" };
		return `Windows ${names[windows[1]] || windows[1]}`;
	}
	const ios = ua.match(/(?:iPhone|iPad|iPod).*? OS ([\d_]+)/);
	if (ios) return `iOS ${ios[1].replace(/_/g, ".")}`;
	const android = ua.match(/Android ([\d.]+)/);
	if (android) return `Android ${android[1]}`;
	const mac = ua.match(/Mac OS X ([\d_.]+)/);
	if (mac) return `macOS ${mac[1].replace(/_/g, ".")}`;
	if (/CrOS/.test(ua)) return "ChromeOS";
	if (/Linux/.test(ua)) return "Linux";
	return "";
}

$(document).on("app_ready", () => {
	const config = frappe.boot.genie_replay;
	if (!config || !config.enabled || frappe.session.user === "Guest" || genie.replay) return;
	genie.replay = new genie.SessionReplay(config);
	genie.replay.start().catch(() => genie.replay && genie.replay.stop());
});
