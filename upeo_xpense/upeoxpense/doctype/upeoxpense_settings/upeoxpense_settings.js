// Copyright (c) 2026, Upeosoft Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("UpeoXpense Settings", {
	test_connection(frm) {
		const phone = frm.doc.test_phone;
		if (!phone) {
			frappe.msgprint(__("Enter a test phone number first."));
			return;
		}
		frappe.call({
			method: "upeo_xpense.upeoxpense.doctype.upeoxpense_settings.upeoxpense_settings.test_connection",
			args: { phone: phone },
			freeze: true,
			freeze_message: __("Sending test message ..."),
			callback(r) {
				if (r.message && r.message.ok) {
					frappe.show_alert(
						{ message: __("Test message sent to {0}", [r.message.phone]), indicator: "green" },
						7
					);
				}
			},
		});
	},
});
