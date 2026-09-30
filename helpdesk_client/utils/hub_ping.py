"""Tell TBO Support a ticket was just raised, so it collects it straight away.

The ping carries only this site's connection id. The hub then pulls the
ticket itself with its own credentials, exactly as its scheduled pull does,
so nothing about the ticket leaves this site through the ping.
"""

import frappe
import requests

PING_TIMEOUT = 10


def notify_hub(doc, method=None):
	"""Support Ticket after_insert: ping the hub once the ticket is committed."""
	settings = frappe.get_cached_doc("HDS Support Settings")
	if not (settings.enabled and settings.client_id and settings.qcs_hub_url):
		return
	frappe.enqueue(
		"helpdesk_client.utils.hub_ping.ping_hub",
		queue="short",
		enqueue_after_commit=True,
	)


def ping_hub():
	settings = frappe.get_cached_doc("HDS Support Settings")
	if not (settings.client_id and settings.qcs_hub_url):
		return
	try:
		requests.post(
			f"{settings.qcs_hub_url.rstrip('/')}/api/method/helpdesk.api.ticket_raised",
			json={"client_id": settings.client_id},
			timeout=PING_TIMEOUT,
		)
	except requests.RequestException:
		# the hub's every-minute pull picks the ticket up anyway
		pass
