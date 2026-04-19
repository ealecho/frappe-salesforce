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

This integration uses Salesforce **External Client Apps** (ECA) with the OAuth 2.0
JWT Bearer flow. Connected Apps also work (the wire protocol is identical),
but Salesforce is steering new integrations toward External Client Apps.

### 1. Generate an RSA key pair

```bash
openssl genrsa -out server.key 2048
openssl req -new -x509 -key server.key -out server.crt -days 3650 \
    -subj "/CN=frappe-salesforce"
```

Keep `server.key` secret — you'll paste its contents into Salesforce Settings.
`server.crt` is what you upload to Salesforce.

### 2. Create an External Client App in Salesforce

1. Setup → **App Manager** → **New External Client App**.
2. Basic Information: name, contact email.
3. **API (Enable OAuth Settings)**:
   - Enable OAuth.
   - Callback URL: `https://login.salesforce.com/services/oauth2/success` (unused by JWT flow but required).
   - **Use digital signatures**: upload `server.crt`.
   - OAuth Scopes: `Manage user data via APIs (api)`, `Perform requests at any time (refresh_token, offline_access)`.
   - Enable **Issue JSON Web Token (JWT)-based access tokens**.
4. Save. Open the app's **Policies** page:
   - App Authorization: **Admin-approved users are pre-authorized**.
   - Save.
5. Assign the integration user's **Profile** or a dedicated **Permission Set** to the app (Policies → Profile/Permission Set related lists).
6. Copy the **Consumer Key** from Settings → OAuth Settings.

### 3. Configure Salesforce Settings in Frappe

Open **Salesforce Settings**, fill in:

- Login URL: `https://login.salesforce.com` (or `https://test.salesforce.com` for sandbox)
- External Client App Consumer Key
- Integration Username (exact Salesforce Username)
- RSA Private Key (PEM) — paste the full contents of `server.key`

Click **Diagnose JWT** to preview the claim we'll send (no network call).
Click **Test Connection** to actually authenticate and run a SOQL query.
Then check **Enabled** and save.

### Troubleshooting `invalid_grant: invalid assertion`

- The integration user is not pre-authorized on the ECA policy (most common).
- Consumer Key mismatch.
- The certificate uploaded to the app doesn't match the private key in Settings.
- `login_url` wrong for this org (production vs sandbox).

After a failed **Test Connection**, open **Error Log** and look for a
`Salesforce JWT Bearer auth failed` entry — it contains the decoded claim and
Salesforce's full response.

## License

MIT
