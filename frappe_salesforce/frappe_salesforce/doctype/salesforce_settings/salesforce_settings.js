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

        frm.add_custom_button(__("Diagnose JWT"), () => {
            frappe.call({
                method: "frappe_salesforce.api.connection.diagnose",
                callback: (r) => {
                    if (!r.message) return;
                    if (!r.message.ok) {
                        frappe.msgprint({
                            title: __("Configuration Problem"),
                            message: r.message.error,
                            indicator: "red",
                        });
                        return;
                    }
                    const m = r.message;
                    const rows = Object.entries(m.claim)
                        .map(([k, v]) => `<tr><td><b>${k}</b></td><td><code>${v}</code></td></tr>`)
                        .join("");
                    const notes = (m.notes || []).map((n) => `<li>${n}</li>`).join("");
                    frappe.msgprint({
                        title: __("JWT Claim Preview"),
                        message: `
                            <p><b>Token URL:</b> <code>${m.token_url}</code></p>
                            <table class="table table-bordered">${rows}</table>
                            <ul>${notes}</ul>
                        `,
                        indicator: "blue",
                        wide: true,
                    });
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
