# Copyright (c) 2023, Wahni IT Solutions Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

from helpdesk_client.utils.session_replay import get_replay_bootinfo


def set_bootinfo(bootinfo):
	genie_settings = frappe.get_cached_doc("HDS Support Settings")
	bootinfo["genie_support_enabled"] = genie_settings.enable_ticket_raising
	# the Support button opens the chat (TBO Copilot Phase 5) when this site is paired and it is on
	bootinfo["genie_chat_enabled"] = bool(
		genie_settings.enable_ticket_raising
		and genie_settings.get("enable_chat")
		and genie_settings.client_id
	)
	bootinfo["genie_max_file_size"] = genie_settings.max_recording_size
	# Recordings and screenshots show the customer's own screens, so they are
	# always private. The Save Recording setting is kept for older sites but
	# can no longer make them public.
	bootinfo["genie_file_type"] = 1

	# Left out entirely when off, so the desk loads none of the recorder.
	replay = get_replay_bootinfo(genie_settings)
	if replay:
		bootinfo["genie_replay"] = replay
