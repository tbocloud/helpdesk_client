# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Server side of session replay: attach the browser-built files to a
Support Ticket and clear them out once the ticket is long finished.

The recording itself lives only in the user's browser until they raise a
ticket with "Attach what I did" ticked (see public/js/session_replay.js).
"""

import frappe
from frappe.utils import add_days, cint, now_datetime

# The hub looks these files up by exact name — keep in step with it.
REPLAY_FILE_NAME = "session-replay.json.gz"
DIAGNOSTICS_FILE_NAME = "session-diagnostics.json"
SESSION_FILE_NAMES = (REPLAY_FILE_NAME, DIAGNOSTICS_FILE_NAME)

RETENTION_DAYS = 30
FINISHED_STATUSES = ("Resolved", "Closed")

DEFAULT_MINUTES = 2
MIN_MINUTES = 1
MAX_MINUTES = 5
DEFAULT_PRIVACY = "Hide numbers and typed values"


def get_replay_bootinfo(settings):
	"""Recorder config for the desk, or None when the recorder must not run."""
	if not (settings.enable_ticket_raising and settings.enable_session_replay):
		return None
	return {
		"enabled": True,
		"minutes": clamp_minutes(settings.replay_minutes),
		"privacy": settings.replay_privacy or DEFAULT_PRIVACY,
	}


def clamp_minutes(minutes):
	"""An unset value on an upgraded site reads as 0 — fall back to the default."""
	minutes = cint(minutes) or DEFAULT_MINUTES
	return min(max(minutes, MIN_MINUTES), MAX_MINUTES)


def attach_session_files(ticket_name, session_replay=None, session_diagnostics=None):
	"""Attach the uploaded replay and diagnostics Files to the new ticket."""
	for file_url, file_name in (
		(session_replay, REPLAY_FILE_NAME),
		(session_diagnostics, DIAGNOSTICS_FILE_NAME),
	):
		if file_url:
			attach_session_file(ticket_name, file_url, file_name)


def attach_session_file(ticket_name, file_url, file_name):
	"""Attach one private upload of the current user under its contract name.

	Frappe renames a clashing upload (``session-replay.json3f2a1c.gz``) while
	the hub finds these files by exact name, so the name is restored here; the
	unique file_url still points at the right file on disk. Only the caller's
	own unattached private upload qualifies, so nobody can pull another
	user's file into their ticket by guessing its URL.
	"""
	name = frappe.db.get_value(
		"File",
		{
			"file_url": file_url,
			"attached_to_name": ("is", "not set"),
			"is_private": 1,
			"owner": frappe.session.user,
		},
		"name",
	)
	if name:
		frappe.db.set_value(
			"File",
			name,
			{
				"attached_to_doctype": "Support Ticket",
				"attached_to_name": ticket_name,
				"file_name": file_name,
			},
			update_modified=False,
		)


def delete_expired_session_replays():
	"""Daily job: delete replay files of tickets finished RETENTION_DAYS ago.

	A replay is a recording of the customer's screen; once support is done
	with the ticket there is no reason to keep it. The ticket's modified time
	stands in for when it was resolved or closed — the status change is the
	last save a finished ticket gets.
	"""
	cutoff = add_days(now_datetime(), -RETENTION_DAYS)
	file = frappe.qb.DocType("File")
	ticket = frappe.qb.DocType("Support Ticket")
	expired = (
		frappe.qb.from_(file)
		.join(ticket)
		.on(ticket.name == file.attached_to_name)
		.select(file.name)
		.where(file.attached_to_doctype == "Support Ticket")
		.where(file.file_name.isin(SESSION_FILE_NAMES))
		.where(ticket.status.isin(FINISHED_STATUSES))
		.where(ticket.modified < cutoff)
	).run(pluck=True)

	for file_name in expired:
		frappe.delete_doc("File", file_name, ignore_permissions=True)
