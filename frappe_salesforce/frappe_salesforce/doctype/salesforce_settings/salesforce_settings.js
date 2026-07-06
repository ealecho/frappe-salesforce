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

        frm.add_custom_button(__("Reset HWMs to Epoch (Full Backfill)"), () => {
            const warning = __(
                "This will reset every Salesforce high-water mark to " +
                "1970-01-01. The next scheduler tick (or 'Sync Now') will " +
                "begin re-fetching every record from the beginning of " +
                "time. This is the recommended action after deploying " +
                "mapping fixes — but it WILL consume significant API " +
                "quota. Per-day budgets still apply.\n\n" +
                "Are you absolutely sure?"
            );
            frappe.confirm(warning, () => {
                frappe.call({
                    method: "frappe_salesforce.api.sync.reset_all_high_water_marks",
                    freeze: true,
                    freeze_message: __("Resetting high-water marks..."),
                    callback: (r) => {
                        if (r.message && r.message.ok) {
                            frappe.msgprint({
                                title: __("Backfill Armed"),
                                message: __(
                                    "All {0} high-water marks reset to {1}. " +
                                    "Trigger 'Sync Now' or wait for the next " +
                                    "scheduler tick. Monitor progress via " +
                                    "Salesforce Sync Log.",
                                    [
                                        r.message.fields.length,
                                        r.message.reset_to,
                                    ]
                                ),
                                indicator: "orange",
                            });
                        }
                    },
                });
            });
        }, __("Danger Zone"));

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

        frm.add_custom_button(__("Retention Report"), () => {
            frappe.call({
                method: "frappe_salesforce.api.sync.retention_backfill_report",
                freeze: true,
                freeze_message: __("Counting Salesforce records..."),
                callback: (r) => {
                    if (!r.message) return;
                    const rows = Object.entries(r.message)
                        .map(([obj, c]) => `<tr><td>${obj}</td><td>${c.total}</td><td>${c.keep}</td><td>${c.drop}</td></tr>`)
                        .join("");
                    frappe.msgprint({
                        title: __("Retention Report"),
                        message: `
                            <table class="table table-bordered">
                                <tr><th>Object</th><th>Total</th><th>Keep</th><th>Drop</th></tr>
                                ${rows}
                            </table>
                        `,
                        indicator: "blue",
                        wide: true,
                    });
                },
            });
        }, __("Retention"));

        frm.add_custom_button(__("Dedup Contacts (Report)"), () => {
            frappe.call({
                method: "frappe_salesforce.api.sync.dedup_contacts",
                args: { dry_run: "true" },
                freeze: true,
                freeze_message: __("Scanning Contacts for duplicates..."),
                callback: (r) => {
                    if (!r.message) return;
                    const m = r.message;
                    const sample = (m.sample || [])
                        .map((s) => `<li>${s.first} ${s.last} &lt;${s.email}&gt; — ${s.names.join(", ")}</li>`)
                        .join("");
                    frappe.msgprint({
                        title: __("Dedup Report (dry run — no changes made)"),
                        message: `
                            <p><b>${m.duplicate_groups}</b> duplicate group(s),
                            <b>${m.records_to_merge}</b> record(s) would be merged.</p>
                            <ul>${sample}</ul>
                        `,
                        indicator: "blue",
                        wide: true,
                    });
                },
            });
        }, __("Retention"));

        frm.add_custom_button(__("Start Retention Backfill"), () => {
            frappe.confirm(
                __(
                    "This re-imports only the records matching the retention " +
                    "policy (see sync/retention.py). It runs as a background " +
                    "job — safe to close this page — and can take a while " +
                    "plus consume significant API quota. Progress and final " +
                    "status (Success / Partial / Failed) are recorded on " +
                    "Salesforce Retention Log.\n\n" +
                    "Continue?"
                ),
                () => {
                    frappe.call({
                        method: "frappe_salesforce.api.sync.start_retention_backfill",
                        callback: () => {
                            frappe.show_alert({
                                message: __(
                                    "Backfill queued — track progress in {0}.",
                                    [`<a href="/app/salesforce-retention-log">${__("Salesforce Retention Log")}</a>`]
                                ),
                                indicator: "blue",
                            });
                        },
                    });
                }
            );
        }, __("Retention"));

        frm.add_custom_button(__("Purge Synced Data"), () => {
            const warning = __(
                "This PERMANENTLY deletes every CRM record the Salesforce " +
                "sync created (Account/Contact/Opportunity/Task/Event), " +
                "tracked via Salesforce Record Link. Manually-entered CRM " +
                "data is never touched. This is meant to precede a " +
                "'Start Retention Backfill' run and cannot be undone. " +
                "It runs as a background job; final status (Success / " +
                "Partial / Failed) is recorded on Salesforce Retention Log.\n\n" +
                "Are you absolutely sure?"
            );
            frappe.confirm(warning, () => {
                frappe.call({
                    method: "frappe_salesforce.api.sync.purge_synced_data",
                    args: { dry_run: "false" },
                    callback: () => {
                        frappe.show_alert({
                            message: __(
                                "Purge queued — track progress in {0}.",
                                [`<a href="/app/salesforce-retention-log">${__("Salesforce Retention Log")}</a>`]
                            ),
                            indicator: "orange",
                        });
                    },
                });
            });
        }, __("Danger Zone"));
    },
});
