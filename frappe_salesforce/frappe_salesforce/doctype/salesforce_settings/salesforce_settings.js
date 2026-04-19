frappe.ui.form.on("Salesforce Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Test Connection"), () => {
            frappe.call({
                method: "frappe_salesforce.api.connection.test_connection",
                freeze: true,
                freeze_message: __("Contacting Salesforce..."),
                callback: (r) => {
                    if (r.message && r.message.ok) {
                        frappe.msgprint({
                            title: __("Connected"),
                            message: __("Connected to Salesforce org {0} ({1})",
                                [r.message.org_name, r.message.org_id]),
                            indicator: "green",
                        });
                    } else {
                        frappe.msgprint({
                            title: __("Connection Failed"),
                            message: (r.message && r.message.error) || __("Unknown error"),
                            indicator: "red",
                        });
                    }
                },
            });
        });

        frm.add_custom_button(__("Sync Now"), () => {
            frappe.call({
                method: "frappe_salesforce.api.sync.trigger_manual_sync",
                callback: () => {
                    frappe.show_alert({
                        message: __("Sync queued"),
                        indicator: "blue",
                    });
                },
            });
        });
    },
});
