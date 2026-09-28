// Copyright (c) 2026, Quark Cyber Systems FZC and contributors
// For license information, please see license.txt

frappe.ui.form.on("Content Approval", {
	refresh(frm) {
		render_images(frm);

		if (frm.doc.status !== "Pending" || frm.is_new()) return;

		frm.add_custom_button(__("Approve"), () => {
			frm.set_value("status", "Approved");
			frm.save().then(() =>
				frappe.show_alert({ message: __("Approved"), indicator: "green" })
			);
		}).addClass("btn-primary");

		frm.add_custom_button(__("Request changes"), () => {
			frappe.prompt(
				{
					fieldname: "comment",
					fieldtype: "Small Text",
					label: __("What should change?"),
					reqd: 1,
				},
				({ comment }) => {
					frm.set_value("client_comment", comment);
					frm.set_value("status", "Changes Requested");
					frm.save().then(() =>
						frappe.show_alert({
							message: __("Sent back to the team"),
							indicator: "orange",
						})
					);
				},
				__("Request changes"),
				__("Send")
			);
		});
	},
});

// Show the design next to the caption so the approver sees exactly what will be published
function render_images(frm) {
	const images = (frm.get_files() || []).filter((f) =>
		/\.(png|jpe?g|gif|webp)$/i.test(f.file_name || f.file_url || "")
	);
	const wrapper = frm.get_field("images_html").$wrapper;
	if (!images.length) {
		wrapper.html(`<p class="text-muted small">${__("No images attached.")}</p>`);
		return;
	}
	wrapper.html(
		`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px">
			${images
				.map(
					(f) => `<a href="${encodeURI(f.file_url)}" target="_blank" rel="noopener">
						<img src="${encodeURI(f.file_url)}" alt="${frappe.utils.escape_html(f.file_name || "")}"
							style="width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px;border:1px solid var(--border-color)">
					</a>`
				)
				.join("")}
		</div>`
	);
}
