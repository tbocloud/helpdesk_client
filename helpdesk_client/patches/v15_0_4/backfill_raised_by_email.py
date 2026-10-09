import frappe

from helpdesk_client.utils.context import raiser_identity


def execute():
	"""Fill the contact email and name on tickets raised before the fields existed."""
	fallback = frappe.db.get_single_value("HDS Support Settings", "fallback_contact_email")
	for name, raised_by in frappe.get_all(
		"Support Ticket",
		filters={"raised_by_email": ("is", "not set"), "raised_by": ("is", "set")},
		fields=["name", "raised_by"],
		as_list=True,
	):
		email, full_name = raiser_identity(raised_by, fallback)
		frappe.db.set_value(
			"Support Ticket",
			name,
			{"raised_by_email": email, "raised_by_name": full_name},
			update_modified=False,
		)
