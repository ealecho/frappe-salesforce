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
                args: { include_assertion: 1 },
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
                    const fp = m.public_key_fingerprint;
                    const fpBlock = fp
                        ? `
                            <h5>Public Key Fingerprint (from your private key)</h5>
                            <p><b>SHA-256 (colon-hex):</b><br/><code style="word-break:break-all">${fp.sha256_colon_hex}</code></p>
                            <p><b>SHA-256 (base64):</b> <code>${fp.sha256_base64}</code></p>
                            <p><i>${m.fingerprint_help || ""}</i></p>
                        `
                        : `<p style="color:#c00">${m.public_key_fingerprint_error || ""}</p>`;
                    const asn = m.signed_assertion
                        ? `
                            <h5>Signed JWT Assertion</h5>
                            <p><i>${m.assertion_help || ""}</i></p>
                            <textarea readonly style="width:100%;height:80px;font-family:monospace;font-size:11px">${m.signed_assertion}</textarea>
                        `
                        : "";
                    frappe.msgprint({
                        title: __("JWT Claim Preview"),
                        message: `
                            <p><b>Token URL:</b> <code>${m.token_url}</code></p>
                            <table class="table table-bordered">${rows}</table>
                            ${fpBlock}
                            <ul>${notes}</ul>
                            ${asn}
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
