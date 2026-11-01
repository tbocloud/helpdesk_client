# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Similar open tickets from colleagues (TBO Copilot Phase 14).

Before TBO Support raises a new ticket from the chat, the site looks among its own open tickets, raised by other
users, for one that looks the same. The user can follow it instead of raising another ("This is my issue, add me to
it"): it shows in their Tickets with its chat, they get its notices, and TBO Support notes that one more person has
the problem. Only a ticket's title, status and number of colleagues are shown, never its description, and never an
HR or payroll ticket.
"""

import re

import frappe
from frappe import _
from frappe.core.utils import html2text
from frappe.utils import cint, now_datetime

from helpdesk_client import chat, inbox

SHOWN = 2
# the ticket is with TBO Support and still open
OPEN_STATUSES = ("Open", "Replied", "Paused")
MIN_SCORE = 4
LOOK_BACK = 300
HR_MODULES = {"HR", "Payroll"}
HR_WORDS = {
	"salary",
	"salaries",
	"payroll",
	"payslip",
	"payslips",
	"leave",
	"leaves",
	"attendance",
	"appraisal",
	"gratuity",
	"bonus",
	"wps",
}
STOP_WORDS = {
	"about",
	"after",
	"again",
	"also",
	"been",
	"before",
	"cannot",
	"could",
	"does",
	"doesn",
	"dont",
	"error",
	"every",
	"from",
	"have",
	"here",
	"into",
	"just",
	"like",
	"more",
	"only",
	"over",
	"please",
	"same",
	"shows",
	"since",
	"some",
	"still",
	"than",
	"that",
	"there",
	"they",
	"this",
	"time",
	"today",
	"under",
	"want",
	"what",
	"when",
	"where",
	"which",
	"while",
	"will",
	"with",
	"won't",
	"wont",
	"work",
	"working",
	"would",
	"your",
}


def enabled() -> bool:
	# on unless switched off: a site that has not saved its settings since the field came keeps it on
	value = frappe.get_cached_doc("HDS Support Settings").get("show_similar_tickets")
	return chat.chat_enabled() and (value is None or cint(value) == 1)


def words(text: str) -> set[str]:
	"""The words that say what a problem is about: four letters or more, without the everyday ones."""
	return {w for w in re.findall(r"[^\W_]{4,}", (text or "").lower()) if w not in STOP_WORDS}


def _hr_doctype(doctype: str) -> bool:
	if not doctype:
		return False
	module = frappe.db.get_value("DocType", doctype, "module")
	if not module:
		return False
	return module in HR_MODULES or frappe.db.get_value("Module Def", module, "app_name") == "hrms"


def _is_hr(t) -> bool:
	return _hr_doctype(t.ref_doctype) or bool(words(t.subject) & HR_WORDS)


def _what_the_chat_is_about(doc) -> tuple[set[str], str, str]:
	"""The words of what the user said and of TBO Support's summary, and the record the chat started on."""
	text = []
	for m in frappe.get_all(
		inbox.MESSAGE,
		filters={"conversation": doc.name},
		fields=["direction", "kind", "text", "card"],
		order_by="creation asc",
	):
		if m.direction == "Customer":
			text.append(m.text or "")
		elif m.kind == "Summary" and m.card:
			card = frappe.parse_json(m.card) or {}
			text += [str(v) for _k, v in card.get("facts") or []]
	return words(" ".join(text)), doc.get("ref_doctype") or "", doc.get("ref_docname") or ""


def _candidates(user: str) -> list:
	mine = set(inbox.followed(user))
	rows = frappe.get_all(
		inbox.TICKET,
		filters={"status": ["in", OPEN_STATUSES], "ticket_id": ["is", "set"]},
		fields=[*inbox.TICKET_FIELDS, "description"],
		order_by="modified desc",
		limit=LOOK_BACK,
	)
	return [t for t in rows if user not in (t.owner, t.raised_by) and t.name not in mine and not _is_hr(t)]


def _score(t, said: set[str], ref_doctype: str, ref_docname: str) -> int:
	score = 2 * len(said & words(t.subject)) + min(
		3, len(said & words(html2text(t.description or "", wrap=False)))
	)
	if ref_doctype and t.ref_doctype == ref_doctype:
		score += 4 if ref_docname and t.ref_docname == ref_docname else 1
	return score


def _colleagues(name: str) -> int:
	return 1 + frappe.db.count(inbox.FOLLOWER, {"parent": name, "parenttype": inbox.TICKET})


def _card(t) -> dict:
	state = inbox.state(t)
	return {
		"name": t.name,
		"summary": inbox.summary(t.subject),
		"dot": state["dot"],
		"line": state["line"],
		"colleagues": _colleagues(t.name),
	}


@frappe.whitelist()
def similar(conversation: str) -> list[dict]:
	"""Up to two open tickets from colleagues that look like this chat's problem."""
	inbox.require_user()
	doc = chat._mine(conversation)
	if doc.ticket or not enabled():
		return []
	said, ref_doctype, ref_docname = _what_the_chat_is_about(doc)
	if not said and not ref_doctype:
		return []
	if said & HR_WORDS or _hr_doctype(ref_doctype):
		return []  # an HR or payroll problem is never matched against colleagues' tickets
	scored = [(_score(t, said, ref_doctype, ref_docname), t) for t in _candidates(frappe.session.user)]
	scored = [pair for pair in scored if pair[0] >= MIN_SCORE]
	scored.sort(key=lambda pair: pair[0], reverse=True)  # stable: equal scores keep the newest first
	return [_card(pair[1]) for pair in scored[:SHOWN]]


@frappe.whitelist(methods=["POST"])
def join(conversation: str, ticket: str) -> dict:
	"""This is my issue, add me to it: the user follows the colleague's ticket, nothing new is raised, and
	TBO Support notes one more person has the problem (its `joined` action closes this chat)."""
	inbox.require_user()
	user = frappe.session.user
	doc = chat._mine(conversation)
	if doc.ticket:
		frappe.throw(_("This chat is about a ticket already."))
	if not enabled():
		frappe.throw(_("Following colleagues' tickets is switched off on this site."), frappe.PermissionError)
	shown = {t.name for t in _candidates(user)}
	if ticket not in shown:
		frappe.throw(_("This ticket can't be followed."), frappe.PermissionError)
	t = frappe.get_doc(inbox.TICKET, ticket)
	frappe.get_doc(
		{
			"doctype": inbox.FOLLOWER,
			"parent": t.name,
			"parenttype": inbox.TICKET,
			"parentfield": "followers",
			"idx": len(t.followers) + 1,
			"user": user,
			"added_on": now_datetime(),
		}
	).insert(ignore_permissions=True)
	t.reload()
	inbox.refresh_for(t)
	told = True
	kept = []
	try:
		reply = chat._relay(
			{
				"action": "joined",
				"conversation": doc.hub_conversation,
				"client_conversation": doc.name,
				"client_ticket": t.name,
				"user": chat._user(),
			}
		)
		kept = chat._keep(doc, reply)
	except chat.ChatUnavailable:
		told = False
	if not told:
		# an older TBO Support has no `joined`: the user follows it here; the chat stays open
		kept = [
			chat._as_dict(
				chat._add(
					doc,
					{
						"direction": "System",
						"kind": "Text",
						"text": _(
							"You now follow {0}. TBO Support could not be told just now; if your case is different, say so here."
						).format(t.name),
					},
				)
			)
		]
	return {"conversation": doc.name, "ticket": t.name, "told": told, "messages": kept}
