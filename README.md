### Helpdesk Client

helpdesk_client

### What TBO Support (the hub) can read here

The hub reaches this site over MCP (`helpdesk_client.mcp.handler.handle`) with the support user's API key, checked on every request. Its read tools obey **HDS Support Settings** (enabled, allowed and blocked doctypes, limits); writes also need **Allow Write Operations**. Besides `get_doc`, `get_list`, `get_count`, `get_meta`, `execute_report`, `get_error_log` (filters by time, method and document; each row names the app it came from and its top frames), `get_installed_apps` and `get_site_info`, the diagnostic tools are:

- `get_code_identity`: per app the version, branch, commit, remotes (credentials removed) and uncommitted changes.
- `get_customizations`: custom fields, property setters, client and server scripts, workflows, print formats and notifications, optionally for some doctypes or since a date.
- `get_deploy_status`: patches run, scheduler, workers, and the errors since a time grouped by signature.
- `get_version_history`: who changed a record and what, each change marked hub, system, import or person.

Every argument that names a doctype, including lists, is checked against the allowed and blocked lists.

### What TBO Support (the hub) may change here

Every write from the hub passes this site's guard (`helpdesk_client.mcp.write_guard`), whatever the hub asks:

1. support enabled, and **Allow Write Operations** on;
2. the doctype not blocked (and in the allowed list when there is one); a table row is judged by the record it belongs to;
3. never users, roles and permissions, system and email settings, OAuth and connected apps, scripts and scheduled jobs, custom fields, property setters, doctypes, workflows, print formats, bulk updates and data imports, or this app's own settings and log;
4. the doctype on the **Write List** (HDS Support Settings) with that action: update, create, or submit and cancel. Nothing is deleted;
5. on a **Production** site (the default), an approval the hub signed with this site's **Approval Key** for exactly that record and those values, and not expired.

The approval key is made by this site when its System Manager connects it to TBO Support (`connect_to_hub`), handed to the hub, and forgotten when the pairing ends. A site paired before this version connects once more to get one. The write list starts empty: a site takes no write from TBO Support until its System Manager fills it.

Corrections use two tools. `check_change` writes nothing and runs none of this site's code: it returns the guard's verdict, any field or value problems, and the record's current values. `apply_change` changes one record: it leaves the record alone when a field it changes no longer holds the approved old value, saves with the site's normal validation, and adds a note to the record's timeline. Every write, applied, refused or failed, is a row in **HDS Change Log** (who approved it, the change set, the old and new values), which this site's System Managers can read.

### Who may raise a ticket here

The Support button (the chat, or the form) is for the customer's own users. TBO Support signed in here as its support user (**Login to site** on the hub) gets a notice instead, and `chat.start`, `chat.send` and `create_ticket` refuse it, so a ticket never names TBO as the customer. Administrator still raises tickets as the site's **Fallback Contact Email**.

### The Support panel: one chat per ticket

With the chat on, the round Support button opens the **Support panel** (`public/js/chat_panel.js`). It has three tabs:

- **Tickets:** a dropdown of the user's tickets. Each shows a dot, the ticket's name and a one-line summary, and opens that ticket's own chat.
- **New chat:** chats that did not become tickets.
- **Action needed:** the red tickets, each with what is needed. Picking one opens its chat.

**Full page** opens the same at `/app/support-chat`, and `/app/support-chat/SUP-…` opens one ticket's chat. The panel and the page share the chat view in `public/js/chat_view.js`; the server side is `inbox.py`.

- **The dots** (`inbox.state`):
  - 🟢 the user confirmed the fix, or the ticket is closed;
  - 🔴 TBO Support waits for the user: a fix to check (Resolved), or an answer (Replied, Waiting on Customer, or the stage Waiting for you);
  - 🟠 the team is working on it.

  A confirm or reopen counts only until TBO Support changes the ticket's status again (`last_synced`), so a ticket fixed a second time asks again.
- **A red button** above the Support button shows **Actions needed · n** while tickets wait for the user. Its count comes from boot and is refreshed live.
- **A new chat** first asks "Is this a new problem, or about one of your open tickets?" and lists them.
- **A ticket raised with the form** gets its chat the first time it is opened (`chat.open_ticket`). Its text and TBO Support's updates come first, then TBO Support links a chat to the ticket (hub action `open_ticket`). Before TBO Support has picked the ticket up, or with an older hub, its story shows read-only.
- **What's the status?** is answered on this site from the ticket (stage, latest update, who has it, what is needed); nobody at TBO Support is asked.
- **Only the user closes a ticket.** In a ticket's chat, **It's fixed**, **Still broken** and **It came back** (on a closed ticket) set the ticket's own confirmation, as its form does. TBO Support applies it once on its next sync (every 5 minutes). A closed ticket's chat takes no more messages.
- **Notices and reminders:**
  - When a ticket turns red, the user gets one notice saying what is needed, linked to its chat.
  - A fix waiting for the user's check is brought up again every 3 days until they answer (`inbox.remind_unconfirmed`, daily).

### Getting help from where the problem is (Phase 14)

- **Get help** on every form (`public/js/get_help.js`, from Frappe's `form-refresh`) opens the panel on a new chat about that record. A bar over the message box says "About Sales Invoice …"; the user can remove it before sending. The chat starts with their first message (`chat.start` with the record).
- **Get help with this error** on Frappe's red message dialog (`frappe.msg_dialog.add_custom_action`) sends the record, the error as shown (500 characters at most) and what the user pressed (Save, Submit, Cancel; read from the form's save call). It is the chat's first message, and TBO Support takes the record and the error as facts, so it does not ask for them again. A line in the dialog says only the record's name and the message go, not the record's contents.
- **The record stays with the ticket:** a ticket raised from the chat keeps `ref_doctype` / `ref_docname` (the chat stores them), its chat links to the record, and the record's form shows a **Support** strip with the user's open tickets about it (`inbox.for_record`).
- **The message box** has **Attach**, **Screenshot** and **Record screen** (`public/js/screen_tools.js`). Files wait in the message box, where an image can be viewed and a video played, and go with the next message. While recording, a bar floats at the bottom of the screen with the time, the voice (on when there is a microphone, can be muted), **Discard** and **Stop and attach**; the panel can stay closed meanwhile. A recording stops by itself after **Longest recording (minutes)** (HDS Support Settings, 3 by default) or at the upload limit. When TBO Support asks for a recording (its **Record** button), it is sent as soon as the user stops. Phones cannot capture the screen, so the two buttons are hidden there.
- **Send a form instead** opens the form with what the user typed, their screenshots, their recording and the record, and opens the new ticket's chat after **Raise Ticket**. TBO Support picks the new ticket up at once, so the chat is live straight away; with an older TBO Support it is read-only until its next pull.
- **Similar open tickets** (`similar.py`, **Show similar tickets from colleagues** in HDS Support Settings, on by default): before TBO Support raises a ticket from the chat, the site shows up to two open tickets from other users that look the same (title, status and how many colleagues; never the description, never HR or payroll). **This is my issue, add me to it** makes the user a follower (**Support Ticket Follower**): they see the ticket and read its chat, get its status and stage notices, but nothing waits for them, and only the raiser answers. TBO Support notes "… has the same problem" on its ticket (hub action `joined`), and nothing new is raised.
- **The panel:** **Ctrl + /** (**Cmd + /** on a Mac) opens and closes it (not inside a code editor); **Esc** closes it and returns to the Support button. Its left edge resizes it (360–640 px, remembered in the browser). On screens 1280 px and wider it docks beside the page, which shrinks; below that, and on the point-of-sale, print and Support pages, it stays over the page.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app helpdesk_client
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/helpdesk_client
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
# helpdesk_client
