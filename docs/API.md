# Nexus River View — REST API v1

Base URL: `https://accounts.pythonicshariful.tech/api/v1`

All responses are JSON. All endpoints except `/health` and `/auth/login` require a
bearer token. Money is always a JSON number rounded to 2 decimals — parse it as
`BigDecimal` in Kotlin, never `Double`.

---

## Authentication

### `POST /auth/login`
```json
{ "username": "admin", "password": "••••" }
```
```json
{
  "data": {
    "token": "eyJ1aWQiOjF9...",
    "token_type": "Bearer",
    "expires_in": 604800,
    "user": { "id": 1, "username": "admin", "is_admin": true }
  }
}
```
Send the token on every request:
```
Authorization: Bearer <token>
```

### `GET /auth/me`
Returns the current user.

### `POST /auth/refresh`
Issues a fresh 7-day token for the current user.

### Admin-password confirmation
Destructive endpoints (create/update/delete of business records) require the admin
password in addition to the token. Send it either:

- header `X-Admin-Password: 9885`, or
- body field `"admin_password": "9885"`.

Without it the API returns `403` with `code: "admin_password_required"`. The Android
app should prompt for the password in a confirmation dialog before every write.

---

## Response envelopes

Success:
```json
{ "data": { ... } }
{ "data": [ ... ], "meta": { "page": 1, "per_page": 50, "total": 312, "pages": 7 } }
```

Error:
```json
{ "error": { "message": "…", "status": 422, "code": "validation_error" } }
```

Status codes: `200` ok, `201` created, `400` bad request, `401` unauthenticated/expired
token, `403` admin password required, `404` not found, `409` conflict (duplicate,
insufficient shares, already paid), `422` validation, `500` internal.

Pagination applies to list endpoints: `?page=1&per_page=50` (max 200).

Dates in API input/output are `YYYY-MM-DD`. Bank-ledger rows are stored internally as
`DD-MM-YYYY` but the API accepts and returns `YYYY-MM-DD`.

---

## Endpoints

### Meta

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Public liveness check |
| GET | `/meta` | Company name, currency, every enum the client needs, date formats |

### Dashboard

| Method | Path | Description |
|---|---|---|
| GET | `/dashboard` | KPIs (project value, collected, due, bank, cash, party balances), 6-month cash-flow chart, entity counts |

### Directors

| Method | Path | Notes |
|---|---|---|
| GET | `/directors` | Paginated |
| GET | `/directors/<id>` | Includes nested `customers[]` |
| POST | `/directors` | `name` required |
| PATCH | `/directors/<id>` | Partial update |
| DELETE | `/directors/<id>` | `409` if the director still owns customers |

### Customers

| Method | Path | Notes |
|---|---|---|
| GET | `/customers` | Filters: `director_id`, `q` (name/id/phone/plot), `due_only=1` |
| GET | `/customers/<id>` | Full profile + `installments[]` + `transactions[]` |
| POST | `/customers` | Requires `director_id`, `name`, `shares`; rejects shares over the director's available total |
| PATCH | `/customers/<id>` | Changing `shares` recalculates totals and installments |
| DELETE | `/customers/<id>` | Removes journal entries and transactions |

### Customer payments (transactions)

| Method | Path | Notes |
|---|---|---|
| GET | `/customers/<id>/transactions` | Newest first |
| POST | `/customers/<id>/transactions` | `amount`, `date`, `payment_source` = `cash`\|`petty_cash`\|`bank`, optional `bank_id`, `customer_installment_id`, `installment_type`, `remarks`, `transaction_id`, `images[]` |
| DELETE | `/transactions/<id>` | Reverses side-effects and recalculates customer totals |

The POST posts a double-entry journal automatically (T-03 / T-04) and allocates the
payment against the selected installment.

### Installments

| Method | Path | Notes |
|---|---|---|
| GET | `/installments` | Includes expected / collected / due totals |
| GET | `/installments/<id>` | Includes `customer_installments[]` |
| POST | `/installments` | `name`, `amount_per_share`; recalculates every customer |
| PATCH | `/installments/<id>` | Recalculates every customer |
| DELETE | `/installments/<id>` | Cascades customer installments |

### Parties

| Method | Path | Notes |
|---|---|---|
| GET | `/party-categories` | |
| POST | `/party-categories` | |
| GET | `/parties` | Filters: `category`, `q` |
| GET | `/parties/<id>` | Includes `ledger[]` |
| POST | `/parties` | `name`, `category` |
| PATCH | `/parties/<id>` | |
| DELETE | `/parties/<id>` | |
| POST | `/parties/<id>/ledger` | `bill_amount`/`paid_amount`, `date`, `description`, `reference`; recomputes running balance |
| DELETE | `/party-ledger/<id>` | Recomputes running balance |

`current_balance` is positive when you owe the party, negative when they hold an advance.

### Petty cash

| Method | Path | Notes |
|---|---|---|
| GET | `/petty-cash` | Filters: `start_date`, `end_date`, `category`; meta contains totals and balance |
| GET | `/petty-cash/categories` | |
| POST | `/petty-cash` | `type` = `Income`\|`Expense`, `amount`, `description`, `category`, `date`; posts journal T-09/T-11 |
| DELETE | `/petty-cash/<id>` | Removes its journal entry |

### Banks

| Method | Path | Notes |
|---|---|---|
| GET | `/banks` | Includes computed `balance` per account |
| GET | `/banks/<id>` | Includes `transactions[]` |
| POST | `/banks` | `bank_name`, `account_no` required |
| PATCH | `/banks/<id>` | |
| DELETE | `/banks/<id>` | |
| POST | `/banks/<id>/transactions` | `tx_type` = `credit`\|`debit`, `amount`, `date`, optional cheque/ref/narration/category; recomputes balances |
| DELETE | `/bank-transactions/<id>` | Recomputed balances |

### Vouchers

| Method | Path | Notes |
|---|---|---|
| GET | `/vouchers` | Filters: `type`, `start_date`, `end_date`, `q` |
| GET | `/vouchers/next-number?type=Debit` | Suggested `voucher_no` |
| GET | `/vouchers/<id>` | |
| POST | `/vouchers` | `type` (`Debit`\|`Credit`), `total_amount`, `amount_paid`, `payment_method` (`Cash`\|`Bank`), optional `bank_id`, `party_id`, `customer_id`, `category`, accounts, `is_payment`, `description`, `notes`, `date` |
| PATCH | `/vouchers/<id>` | Reposts all financial side-effects |
| DELETE | `/vouchers/<id>` | Unwinds cash, bank, party and journal effects |

The server posts the balanced journal entry. Do not compute debit/credit yourself;
send the business fields and let the engine produce the entries.

### Contra transfers

| Method | Path | Notes |
|---|---|---|
| GET | `/contras` | Date filtered |
| GET | `/contras/next-number` | |
| POST | `/contras` | `from_account`/`to_account` (`Cash`\|`Bank`), `amount`, optional `bank_id`, `cheque_no`, `description` |
| DELETE | `/contras/<id>` | |

### Chart of accounts & journal

| Method | Path | Notes |
|---|---|---|
| GET | `/accounts` | Filters: `type`, `q` |
| POST | `/accounts` | `account_code`, `account_name`, `account_type`, `account_category`, `normal_balance` |
| DELETE | `/accounts/<code>` | `409` for system accounts, accounts with activity, or children |
| GET | `/journal` | Filters: `reference_type`, `start_date`, `end_date`, `q`; includes lines |
| GET | `/journal/<id>` | |
| POST | `/journal/<id>/reverse` | Creates a reversing entry (T-21) |

### Reports (read-only)

| Method | Path | Query |
|---|---|---|
| GET | `/reports/trial-balance` | `start_date`, `end_date` |
| GET | `/reports/profit-loss` | `start_date`, `end_date` |
| GET | `/reports/balance-sheet` | `as_of_date` |
| GET | `/reports/cash-bank-flow` | `start_date`, `end_date` (defaults to current month) |
| GET | `/reports/money-flow` | none |
| GET | `/reports/daily-cash` | `date` |

`trial-balance` returns `"balanced": true|false` — surface that prominently in the app.

### Employees, attendance, leave, salary

| Method | Path | Notes |
|---|---|---|
| GET | `/employees` | Filter `q` |
| POST | `/employees` | `employee_id`, `name`, `net_salary`, leave allocations |
| PATCH | `/employees/<id>` | |
| DELETE | `/employees/<id>` | |
| GET | `/attendance` | `date`, `start_date`, `end_date`, `employee_id` |
| POST | `/attendance` | `{ "date": "YYYY-MM-DD", "records": [{ "employee_id": 1, "status": "Present", "in_time": "09:00", "out_time": "18:00" }] }` — upserts |
| GET | `/leaves` | `employee_id`, `status` |
| POST | `/leaves` | `employee_id`, `leave_type` (`CL`/`ML`/`FL`/`EL`), `from_date`, `to_date`, `reason`; days computed server-side |
| PATCH | `/leaves/<id>` | Approve / reject by status |
| DELETE | `/leaves/<id>` | |
| GET | `/salary` | `month` (`01`–`12`), `year` |
| POST | `/salary/generate` | `month_year` (`YYYY-MM`), optional `employee_ids[]`; applies Friday off-days and the 3-lates-equals-1-absent rule, then posts payroll journal |
| POST | `/salary/<id>/paid` | Posts salary-payment journal |
| POST | `/salary/<id>/unpaid` | Reverses it |

### Todos (per authenticated user)

| Method | Path | Notes |
|---|---|---|
| GET | `/todos` | `today=1`, `open=1` |
| POST | `/todos` | `task`, optional `category`, `due_date`, `due_time` |
| PATCH | `/todos/<id>` | |
| POST | `/todos/<id>/toggle` | |
| DELETE | `/todos/<id>` | |

---

## curl examples

```bash
# Sign in
curl -s -X POST https://accounts.pythonicshariful.tech/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"9885"}'

# Dashboard
TOKEN=<token>
curl -s https://accounts.pythonicshariful.tech/api/v1/dashboard \
  -H "Authorization: Bearer $TOKEN"

# Create a credit voucher (money in) — requires both token and admin password
curl -s -X POST https://accounts.pythonicshariful.tech/api/v1/vouchers \
  -H "Authorization: Bearer $TOKEN" \
  -H 'X-Admin-Password: 9885' \
  -H 'Content-Type: application/json' \
  -d '{"type":"Credit","date":"2026-10-18","total_amount":250000,"amount_paid":250000,
       "payment_method":"Cash","customer_id":12,"category":"Installment",
       "description":"Installment 7"}'

# Trial balance
curl -s 'https://accounts.pythonicshariful.tech/api/v1/reports/trial-balance?start_date=2026-01-01' \
  -H "Authorization: Bearer $TOKEN"
```

---

## Security notes for the Android client

- Store the token in EncryptedSharedPreferences / Android Keystore, never plain SharedPreferences.
- Never persist the admin password; prompt for it per action, keep it in memory only.
- The API is HTTPS-only; do not enable cleartext traffic in the manifest.
- Tokens expire after 7 days; on `401 token_expired`, return to the login screen.
- Do not cache financial reports to external storage.
