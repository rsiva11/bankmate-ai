# Synthetic Demo Data

Everything in `demo_data.json` is **fictional**. Names, masked account numbers,
balances and transactions are invented for this educational project and do not
describe any real person or SBI customer.

| Customer | Purpose in the demo | Expected behaviour |
|---|---|---|
| CUST1001 Aarav Sharma | Clean baseline | No risk alerts; loan of Rs 2,00,000 within demo limits |
| CUST1002 Priya Nair | Risk showcase | Large overseas transfer + 4 online purchases within 10 minutes |
| CUST1003 Rohan Mehta | Repeat-amount + loan showcase | Three identical Rs 4,999 payments; Rs 2,00,000 loan falls outside the demo DTI limit |
| CUST1004 Meera Iyer | High-income baseline | No alerts; strong loan estimate |

Transaction fields: `txn_id`, `timestamp` (ISO 8601), `description`, `amount`
(INR, always positive), `type` (`credit`/`debit`), `category`, `location`,
`risk_indicator` (synthetic demo flag or `null`).

Risk indicators are only inputs to transparent demo rules. They never mean confirmed fraud.
