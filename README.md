# Frappe Salesforce

One-way Salesforce → Frappe CRM integration using SOQL over the Salesforce REST API.

## Features

- OAuth 2.0 JWT Bearer authentication (server-to-server)
- Incremental sync every 15 minutes via `SystemModstamp`
- Configurable field mappings per Salesforce object (data, not code)
- Multi-input mappings for compound fields: addresses, multi-channel emails / phones
- Syncs Users (for owner mapping), Accounts, Contacts, Leads, Opportunities, Tasks, Events
- Deletion sync (daily) via Salesforce `getDeleted` endpoint
- Sync Log with per-object stats and SOQL audit
- Workspace with dashboard charts and KPI number cards
- Full-backfill ("Reset HWMs to Epoch") and date-windowed backfill from the Salesforce Settings UI

## Post-deploy data refresh

After installing or upgrading this app you should refresh existing data from
Salesforce so prior records pick up new mappings and bug fixes.

1. `bench --site <site> migrate` — runs the v0.1.0 patches: creates the
   `custom_sf_*` fields on existing sites, extends default mappings (additively,
   never clobbering user customisations), and rewrites known-buggy rows from
   v0.0.x (e.g. `Opportunity.Amount → annual_revenue` becomes
   `Amount → deal_value`).
2. Open **Salesforce Settings** → **Danger Zone** → **Reset HWMs to Epoch
   (Full Backfill)** → confirm.
3. Wait for the next 15-minute scheduler tick or click **Sync Now**. Records
   are upserted by `custom_salesforce_id`; existing Frappe rows are updated
   in place (no duplicates).
4. Monitor progress via **Salesforce Sync Log**. The per-day API budget
   (default 50,000) caps daily burn; large orgs may take several days to
   fully replay.

The reset is non-destructive in Frappe terms but is one-way — any locally
edited fields that also exist in a SF mapping will be overwritten by the
SF value. Fields not covered by mappings are untouched.

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

**No Consumer Secret is used.** JWT Bearer flow proves identity by signing
the assertion with your RSA private key, not by transmitting a secret.
Leave any "Consumer Secret" field in Salesforce alone — it's for other flows.

### 1. Generate an RSA key pair

On the machine where Frappe runs:

```bash
openssl genrsa -out salesforce.key 2048
openssl req -new -x509 -key salesforce.key -out salesforce.crt -days 3650 \
    -subj "/CN=frappe-salesforce"
```

- `salesforce.key` — the private key. You paste its contents into Frappe Settings. Keep it secret.
- `salesforce.crt` — the self-signed certificate. You upload it to Salesforce.

Verify the pair matches (both hashes must be identical):

```bash
openssl x509 -in salesforce.crt -pubkey -noout | openssl sha256
openssl rsa -in salesforce.key -pubout 2>/dev/null | openssl sha256
```

### 2. Create an External Client App in Salesforce

Setup → **External Client App Manager** → **New External Client App**.

#### Basic Information
- External Client App Name: e.g. `SmartOps_dev`
- API Name: auto-filled
- Contact Email: your admin email
- Distribution State: set per your org's policy

#### App Settings → OAuth Settings
- **Callback URL**: `http://localhost/callback` (required field; JWT Bearer flow does not use it)
- **Selected OAuth Scopes**:
  - `Manage user data via APIs (api)`
  - `Perform requests at any time (refresh_token, offline_access)`
  - Optionally `Access the identity URL service (id, profile, email, address, phone)`
  - Avoid `Full access (full)` — prefer least-privilege

#### Flow Enablement (CRITICAL)
- ☑ **Enable JWT Bearer Flow** ← **this is required; without it Salesforce rejects every JWT with `invalid_grant: invalid assertion`**

Do **not** enable Client Credentials, Device, Authorization Code, or Token Exchange flows unless you have a separate reason.

#### Certificate Upload
When you check "Enable JWT Bearer Flow", a **Certificate Upload** field appears.

- Click **Select a certificate** and upload `salesforce.crt` from Step 1.

#### Security
- ☑ **Issue JSON Web Token (JWT)-based access tokens for named users** (recommended)
- Leave PKCE, refresh-rotation etc. at defaults unless your org requires otherwise

#### Save the app
Click **Create**.

### 3. Configure the Policy (pre-authorize your user)

After saving, open the app again. Go to the **Policies** tab (or equivalent "Policy" section).

- **OAuth Policies → App Authorization**: set to **Admin-approved users are pre-authorized**
- Save.
- Then assign either:
  - **Profiles**: add the integration user's Profile to the policy, OR
  - **Permission Sets**: add a Permission Set that's assigned to the integration user

**If you skip this step, Salesforce returns `user hasn't approved consumer` in Login History** (and the generic `invalid assertion` to our app).

Policy changes can take 2–10 minutes to propagate. Wait before testing.

### 4. Copy the Consumer Key

Open the ECA → **Settings → OAuth Settings → Consumer Key and Secret → Copy** the Consumer Key.

Ignore the Consumer Secret — JWT Bearer flow does not use it.

### 5. Configure Salesforce Settings in Frappe

Open **Salesforce Settings** in Frappe, fill in:

- **Login URL**: `https://login.salesforce.com` (production) or `https://test.salesforce.com` (sandbox)
- **External Client App Consumer Key**: from step 4
- **Integration Username**: the integration user's Salesforce **Username** (Setup → Users → Users → Username column). This is NOT the same as Email Alias or Nickname.
- **RSA Private Key (PEM)**: paste the full contents of `salesforce.key` including the `-----BEGIN` / `-----END` lines

Click **Diagnose JWT**:
- Verify `iss`, `sub`, `aud` values
- Compare **Public Key Fingerprint (SHA-256 colon-hex)** to the fingerprint Salesforce shows for your uploaded cert. They must match.
- Optionally copy the **Signed JWT Assertion** and validate it on https://jwt.io against `salesforce.crt` — if jwt.io reports "Signature Verified", the client side is 100% correct and any remaining failure is in the ECA config.

Click **Test Connection**. On success you'll see the Org Id and Name.

Then check **Enabled** and save.

### Troubleshooting `invalid_grant: invalid assertion`

This error is deliberately opaque from Salesforce. Work through these in order:

1. **Is "Enable JWT Bearer Flow" checked on the ECA?** This is the #1 cause. Go to the app → Settings → Flow Enablement.
2. **Is the integration user pre-authorized?** Check the ECA Policy → App Authorization is "Admin-approved users are pre-authorized" AND the user's Profile or Permission Set is assigned.
3. **Does the fingerprint match?** Click **Diagnose JWT** in Frappe and compare the SHA-256 fingerprint to Salesforce's cert fingerprint.
4. **Is the Username exact?** Setup → Users → Users → copy the Username field value exactly. It's often NOT the user's email.
5. **Production vs sandbox?** If `*.sandbox.my.salesforce.com` is in your browser URL, Login URL must be `https://test.salesforce.com`.
6. **Check Setup → Login History** filtered by the integration user. The Status column shows SF's real rejection reason (far more specific than the token endpoint returns).
7. **Wait for propagation.** After saving ECA policy changes, wait 2–10 minutes.

After a failed **Test Connection**, Frappe's **Error Log** contains a
`Salesforce JWT Bearer auth failed` entry with the decoded JWT claim and
the full Salesforce response for offline review.

## License

MIT
