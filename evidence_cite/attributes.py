from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from .text import normalise

# claim name -> (kind of document it must be cited from, label the cited line must carry)
CLAIMS = {
    "po_total": ("po", "order total:"),
    "po_date": ("po", "date:"),
    "po_vendor": ("po", "vendor:"),
    "invoice_total": ("invoice", "total due:"),
    "invoice_date": ("invoice", "invoice date:"),
    "invoice_vendor": ("invoice", "bill from:"),
    "approver_limit": ("approval", "approval limit:"),
}

_MONEY = re.compile(r"^\$?(\d{1,3}(,\d{3})+|\d+)(\.\d{2})?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_money(value: str) -> Decimal:
    v = value.strip()
    if not _MONEY.match(v):
        raise ValueError(f"not an amount: {value!r}")
    return Decimal(v.lstrip("$").replace(",", ""))


def parse_date(value: str) -> date:
    v = value.strip()
    if not _DATE.match(v):
        raise ValueError(f"not an ISO date: {value!r}")
    return date.fromisoformat(v)


def parse_name(value: str) -> str:
    name, _ = normalise(value)
    if not name:
        raise ValueError("empty name")
    return name


@dataclass(frozen=True)
class Rule:
    claims: tuple[str, ...]  # sorted
    decide: Callable[[dict[str, str]], str]


def _verdict(ok: bool) -> str:
    return "pass" if ok else "exception"


def _amount_match(v: dict[str, str]) -> str:
    return _verdict(parse_money(v["po_total"]) == parse_money(v["invoice_total"]))


def _invoice_after_po(v: dict[str, str]) -> str:
    return _verdict(parse_date(v["invoice_date"]) >= parse_date(v["po_date"]))


def _approval_within_limit(v: dict[str, str]) -> str:
    return _verdict(parse_money(v["approver_limit"]) >= parse_money(v["po_total"]))


def _vendor_match(v: dict[str, str]) -> str:
    return _verdict(parse_name(v["po_vendor"]) == parse_name(v["invoice_vendor"]))


ATTRIBUTES = {
    "amount_match": Rule(("invoice_total", "po_total"), _amount_match),
    "invoice_after_po": Rule(("invoice_date", "po_date"), _invoice_after_po),
    "approval_within_limit": Rule(("approver_limit", "po_total"), _approval_within_limit),
    "vendor_match": Rule(("invoice_vendor", "po_vendor"), _vendor_match),
}


def parse_claim(name: str, value: str) -> None:
    """Raise ValueError when `value` cannot be read as the kind of thing claim `name` holds."""
    if name in ("po_total", "invoice_total", "approver_limit"):
        parse_money(value)
    elif name in ("po_date", "invoice_date"):
        parse_date(value)
    else:
        parse_name(value)
