import math
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import json

from app.utils.serialization import to_json_safe


def test_values_become_json_safe():
    row = [Decimal("12.50"), Decimal("7"), date(2026, 1, 2), datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc), time(1, 2),
           timedelta(minutes=2), uuid.UUID(int=1), b"\x01\xff", float("nan"), float("inf"), None, True, [Decimal("1.5")], {"k": Decimal("2")}]
    out = to_json_safe(row)
    json.dumps(out)  # must not raise
    assert out[0] == 12.5 and out[1] == 7 and isinstance(out[1], int)
    assert out[2] == "2026-01-02" and out[3].startswith("2026-01-02T03:04")
    assert out[5] == 120.0 and out[7] == "\\x01ff"
    assert out[8] is None and out[9] is None and out[10] is None and out[11] is True
    assert out[12] == [1.5] and out[13] == {"k": 2}


def test_large_decimal_does_not_lose_integer_type():
    assert to_json_safe(Decimal("1000000")) == 1000000
    assert not math.isnan(to_json_safe(Decimal("0.1")))
