# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Post-install and post-uninstall hooks for Helpdesk Support Client."""

import frappe

from helpdesk_client.support_user import DEFAULT_SUPPORT_USER, get_support_user

DEFAULT_BLOCKED_DOCTYPES = [
	"User",
	"Email Account",
	"Email Domain",
	"OAuth Client",
	"Social Login Key",
]


def after_install():
	"""Create support user with API keys and default settings."""
	_create_support_user()
	_create_default_settings()
	create_genie_folder()


def after_uninstall():
	"""Disable the support user and revoke the hub's keys."""
	from helpdesk_client.api import revoke_support_keys

	support_user = get_support_user()
	if frappe.db.exists("User", support_user):
		revoke_support_keys()
		frappe.db.set_value("User", support_user, "enabled", 0)
		frappe.db.commit()  # install hook: keep each setup step even if a later one fails - nosemgrep
		print(f"Disabled user {support_user}")


def _create_support_user():
	"""Create or enable the hub's support user (HDS Support Settings) with System Manager role.

	API keys are NOT generated here - they are created during the Hub
	onboarding/registration process to avoid exposing credentials in logs.
	"""
	support_user = get_support_user()
	if frappe.db.exists("User", support_user):
		user = frappe.get_doc("User", support_user)
		if not user.enabled:
			user.enabled = 1
			user.save(ignore_permissions=True)
			print(f"Re-enabled existing user {support_user}")
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": support_user,
				"first_name": "Helpdesk Support",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "System Manager"}],
			}
		)
		user.insert(ignore_permissions=True)
		print(f"Created user {support_user}")

	frappe.db.commit()  # install hook: keep each setup step even if a later one fails - nosemgrep


def _create_default_settings():
	"""Create default HDS Support Settings with blocked doctypes."""
	settings = frappe.get_single("HDS Support Settings")

	if not settings.enabled:
		settings.enabled = 1

	if not settings.support_user:
		settings.support_user = get_support_user() or DEFAULT_SUPPORT_USER

	if not settings.blocked_doctypes:
		for dt in DEFAULT_BLOCKED_DOCTYPES:
			settings.append("blocked_doctypes", {"doctype_name": dt})

	# a new connection keeps HR and payroll private until this site's System Manager opens them (Phase 23 B16)
	settings.block_hr_payroll = 1

	if not settings.max_list_limit:
		settings.max_list_limit = 100

	if not settings.max_report_rows:
		settings.max_report_rows = 500

	settings.save(ignore_permissions=True)
	frappe.db.commit()  # install hook: keep each setup step even if a later one fails - nosemgrep
	print("Default HDS Support Settings created")


def create_genie_folder():
	f = frappe.new_doc("File")
	f.file_name = "Genie"
	f.is_folder = 1
	f.folder = "Home"
	f.insert(ignore_if_duplicate=True)


def make_recordings_private() -> list[str]:
	"""Recordings and screenshots attached to tickets as public files become private: saving the File with
	is_private moves it under /private/files, and the ticket's recording link follows. Run once by the
	v15_0_3 patch and again after every migrate: a file that could not be moved (a permission error on
	disk, a name already taken) is logged and tried again next time, and never stops a migrate, which on
	a customer's site is their deploy. Returns the files still public."""
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Support Ticket", "is_private": 0},
		fields=["name", "file_url"],
	)
	failed = []
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
		except FileNotFoundError:
			continue  # gone from disk: nothing is left that anyone could read
		except Exception:
			frappe.db.rollback()  # this file's change, and its move on disk with it
			frappe.log_error(f"Could not make recording {row.name} private")
			failed.append(row.name)
		# each file moved is kept with its record, whatever happens to the next one
		frappe.db.commit()  # nosemgrep
	return failed
