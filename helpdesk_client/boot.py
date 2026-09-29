# Copyright (c) 2023, Wahni IT Solutions Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

from helpdesk_client.utils.session_replay import get_replay_bootinfo


def set_bootinfo(bootinfo):
	genie_settings = frappe.get_cached_doc("HDS Support Settings")
	bootinfo["genie_support_enabled"] = genie_settings.enable_ticket_raising
	bootinfo["genie_max_file_size"] = genie_settings.max_recording_size
	bootinfo["genie_file_type"] = 1 if genie_settings.save_recording == "Private" else 0

	# Left out entirely when off, so the desk loads none of the recorder.
	replay = get_replay_bootinfo(genie_settings)
	if replay:
		bootinfo["genie_replay"] = replay
