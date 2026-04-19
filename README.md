# Frappe Salesforce

One-way Salesforce → Frappe CRM integration using SOQL over the Salesforce REST API.

## Features

- OAuth 2.0 JWT Bearer authentication (server-to-server)
- Incremental sync every 15 minutes via `SystemModstamp`
- Configurable field mappings per Salesforce object
- Syncs Users (for owner mapping), Accounts, Contacts, Leads, Opportunities, Tasks, Events
- Deletion sync (daily) via Salesforce `getDeleted` endpoint
- Sync Log with per-object stats and SOQL audit
- Workspace with dashboard charts and KPI number cards

## Scope (v1)

| Salesforce Object | Frappe CRM DocType |
|---|---|
| Account | CRM Organization |
| Contact | Contact |
| Lead | CRM Lead |
| Opportunity | CRM Deal |
| Task / Event | CRM Task |

## Installation

```bash
cd ~/frappe-bench
bench get-app https://github.com/YOUR_ORG/frappe-salesforce.git
bench --site your-site.local install-app frappe_salesforce
bench --site your-site.local migrate
bench restart
bench --site your-site.local enable-scheduler
```

## Configuration

1. Create a Connected App in Salesforce with digital signatures enabled (upload your RSA public key / self-signed cert).
2. Pre-authorize the integration user in the Connected App's policies.
3. Open **Salesforce Settings** in Frappe, fill in:
   - Instance URL, Login URL (`https://login.salesforce.com` or test)
   - Connected App Consumer Key (client_id)
   - Integration user username
   - RSA private key PEM
4. Click **Test Connection**.
5. Enable the integration.

## License

MIT
