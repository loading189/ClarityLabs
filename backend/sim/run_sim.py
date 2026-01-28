import random
import uuid
import time
from datetime import datetime, timezone
import requests

API = "http://127.0.0.1:8000"

def plaid_like_payload(amount: float, desc: str):
    return {
        "transaction_id": str(uuid.uuid4()),
        "name": desc,
        "amount": abs(amount),
        "iso_currency_code": "USD",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "pending": False,
    }

def main(business_id: str):
    merchants = ["Gusto Payroll", "Sysco", "Home Depot", "Shell", "Meta Ads", "AWS", "Rent Payment", "Insurance Premium"]
    while True:
        desc = random.choice(merchants)
        amt = random.uniform(20, 900)
        # crude: some are inflow-ish
        if desc in ["Sysco", "Home Depot", "Shell", "Meta Ads", "AWS", "Rent Payment", "Insurance Premium", "Gusto Payroll"]:
            signed = -amt
        else:
            signed = amt

        payload = plaid_like_payload(signed, desc)

        body = {
            "business_id": business_id,
            "source": "plaid_sim",
            "source_event_id": payload["transaction_id"],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        r = requests.post(f"{API}/raw_events", json=body, timeout=10)
        print(r.status_code, r.json())

        time.sleep(random.uniform(0.4, 2.0))

if __name__ == "__main__":
    # paste a real business UUID here after onboarding
    main("00000000-0000-0000-0000-000000000000")
