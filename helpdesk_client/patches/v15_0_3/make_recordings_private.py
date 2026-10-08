# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Recordings and screenshots attached to tickets become private files.

Sites that never set Save Recording uploaded them as public files, readable
by anyone with the link. Saving the File with is_private moves it under
/private/files; the ticket's recording link follows.
"""

import frappe


def execute():
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Support Ticket", "is_private": 0},
		fields=["name", "file_url"],
	)
	for row in files:
		try:
			doc = frappe.get_doc("File", row.name)
			doc.is_private = 1
			doc.save(ignore_permissions=True)
			if doc.file_url != row.file_url:
				frappe.db.set_value(
					"Support Ticket",
					{"screen_recording": row.file_url},
					"screen_recording",
					doc.file_url,
					update_modified=False,
				)
		except Exception:
			frappe.log_error(f"Could not make recording {row.name} private")
