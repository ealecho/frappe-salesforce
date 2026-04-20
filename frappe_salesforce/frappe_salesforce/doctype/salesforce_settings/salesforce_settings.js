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

        frm.add_custom_button(__("API Usage"), () => {
            frappe.call({
                method: "frappe_salesforce.api.sync.get_api_usage",
                callback: (r) => {
                    if (!r.message) return;
                    const m = r.message;
                    const sf_pct = m.sf_limit
                        ? ((m.sf_used / m.sf_limit) * 100).toFixed(1)
                        : "–";
                    const day_pct = m.per_day_budget
                        ? ((m.app_calls_today / m.per_day_budget) * 100).toFixed(1)
                        : "–";
                    frappe.msgprint({
                        title: __("API Usage"),
                        message: `
                            <p><b>Salesforce org quota (last observed):</b><br>
                            ${m.sf_used} / ${m.sf_limit} (${sf_pct}%)<br>
                            <small>observed at ${m.sf_observed_at || "never"}</small></p>
                            <p><b>App-level daily counter:</b><br>
                            ${m.app_calls_today} / ${m.per_day_budget} (${day_pct}%)</p>
                            <p><b>Per-tick budget:</b> ${m.per_tick_budget}</p>
                        `,
                        indicator: "blue",
                    });
                },
            });
        }, __("Diagnostics"));

        frm.add_custom_button(__("Backfill From Date"), () => {
            frappe.prompt(
                [
                    {
                        fieldname: "since",
                        label: __("Backfill from (UTC datetime)"),
                        fieldtype: "Datetime",
                        reqd: 1,
                        description: __(
                            "All high-water marks will be reset to this value. " +
                            "The next sync tick will fetch every record modified since. " +
                            "This can consume significant API quota — use sparingly."
                        ),
                    },
                ],
                (values) => {
                    frappe.confirm(
                        __("Reset every high-water mark to {0}? " +
                           "The next sync will backfill from that point.",
                           [values.since]),
                        () => {
                            frappe.call({
                                method: "frappe_salesforce.api.sync.backfill_from_date",
                                args: { since: values.since },
                                callback: (r) => {
                                    if (r.message && r.message.ok) {
                                        frappe.msgprint({
                                            title: __("Backfill Armed"),
                                            message: __(
                                                "High-water marks reset to {0}. " +
                                                "Trigger 'Sync Now' or wait for the next " +
                                                "scheduler tick.",
                                                [r.message.reset_to]
                                            ),
                                            indicator: "orange",
                                        });
                                    }
                                },
                            });
                        }
                    );
                },
                __("Backfill From Date"),
                __("Reset High-Water Marks")
            );
        }, __("Danger Zone"));
    },
});
