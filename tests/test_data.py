import json
from datetime import datetime

from config import get_settings


def load():
    with open(get_settings().demo_data_path, encoding="utf-8") as f:
        return json.load(f)


def test_dataset_shape_and_synthetic_marker():
    data = load()
    assert "SYNTHETIC" in data["_meta"]["notice"]
    ids = [c["customer_id"] for c in data["customers"]]
    assert len(ids) >= 4 and len(ids) == len(set(ids))
    txn_ids = []
    for c in data["customers"]:
        assert c["transactions"] and c["monthly_income"] > 0
        for t in c["transactions"]:
            assert t["amount"] > 0 and t["type"] in {"credit", "debit"}
            datetime.fromisoformat(t["timestamp"])
            txn_ids.append(t["txn_id"])
    assert len(txn_ids) == len(set(txn_ids))
