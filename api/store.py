"""Read-only access to the synthetic dataset (stands in for a core-banking database)."""
import json
import re
from functools import lru_cache
from typing import Optional

from config import get_settings

CUSTOMER_ID_RE = re.compile(r"^CUST\d{4}$")


@lru_cache(maxsize=4)
def _load(path_str: str) -> dict:
    with open(path_str, encoding="utf-8") as f:
        return json.load(f)


def all_customers() -> list:
    return _load(str(get_settings().demo_data_path))["customers"]


def find_customer(customer_id: str) -> Optional[dict]:
    for c in all_customers():
        if c["customer_id"] == customer_id:
            return c
    return None
