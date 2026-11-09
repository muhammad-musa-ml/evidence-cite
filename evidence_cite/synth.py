from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from .attributes import ATTRIBUTES
from .models import Document

VENDORS = (
    "Harlow Supply Co", "Brightwater Logistics", "Ketterer Industrial", "Pinecrest Packaging",
    "Alder & Finch Tools", "Marrow Cold Storage", "Tidewell Fasteners", "Quarry Lane Metals",
    "Sable Ridge Freight", "Corvin Electrical", "Yarrow Plastics", "Dunmore Safety Gear",
)
APPROVERS = ("R. Okafor", "L. Brandt", "T. Vasquez", "M. Ishikawa", "D. Hale", "P. Nowak")
ITEMS = ("steel brackets", "pallet wrap", "cable ties", "gasket sets", "safety gloves", "bearing kits")
LIMITS = (Decimal(250), Decimal(1000), Decimal(2500), Decimal(10000), Decimal(25000), Decimal(100000))

# Characters an OCR step confuses with each other.
CONFUSABLE = ("0Oo", "1lI", "5Ss", "8B", "2Z")
_GROUP_OF = {ch: group for group in CONFUSABLE for ch in group}


@dataclass(frozen=True)
class Anchor:
    kind: str  # "po", "invoice" or "approval"
    page: int  # 1-based
    line: str
    value: str


@dataclass(frozen=True)
class Sample:
    sample_id: str
    clean: tuple[Document, ...]
    docs: tuple[Document, ...]  # what a checker reads; equals clean unless noise was added
    truth: dict  # attribute -> "pass" or "exception"
    anchors: dict  # claim name -> Anchor: the line that holds the value
    decoys: dict  # claim name -> Anchor: a real line a careless reader takes instead

    def corpus(self) -> dict[str, Document]:
        return {d.doc_id: d for d in self.docs}

    def page(self, doc_kind: str, page: int, clean: bool = False) -> str:
        docs = self.clean if clean else self.docs
        for d in docs:
            if d.doc_id == f"{self.sample_id}/{doc_kind}":
                return d.pages[page - 1]
        raise KeyError(doc_kind)


def money(x: Decimal) -> str:
    return format(x, ",.2f")


def _sample(rng: random.Random, number: int, exception_rate: float) -> Sample:
    sid = f"S{number:04d}"
    flags = {a: rng.random() < exception_rate for a in ATTRIBUTES}

    vendor = rng.choice(VENDORS)
    item = rng.choice(ITEMS)
    qty = rng.randint(5, 60)
    unit = Decimal(rng.randint(6000, 90000)) / 100
    freight = rng.choice((Decimal("0.00"), Decimal("18.50"), Decimal("42.00")))
    po_total = qty * unit + freight
    po_date = date(2026, 1, 5) + timedelta(days=rng.randint(0, 270))
    po_no, inv_no = f"PO-{rng.randint(1000, 9999)}", f"INV-{rng.randint(1000, 9999)}"

    inv_total = po_total
    if flags["amount_match"]:
        inv_total += rng.choice((-1, 1)) * Decimal(rng.randint(100, 25000)) / 100
    if flags["invoice_after_po"]:
        inv_date = po_date - timedelta(days=rng.randint(1, 20))
    else:
        inv_date = po_date + timedelta(days=rng.randint(3, 40))
    if flags["approval_within_limit"]:
        limit = max(t for t in LIMITS if t < po_total)
    else:
        limit = min(t for t in LIMITS if t >= po_total)
    inv_vendor = rng.choice([v for v in VENDORS if v != vendor]) if flags["vendor_match"] else vendor

    subtotal = inv_total - freight
    lines = {
        "po_total": f"Order total: {money(po_total)}",
        "po_date": f"Date: {po_date.isoformat()}",
        "po_vendor": f"Vendor: {vendor}",
        "po_unit": f"Unit price: {money(unit)}",
        "inv_total": f"Total due: {money(inv_total)}",
        "inv_date": f"Invoice date: {inv_date.isoformat()}",
        "inv_vendor": f"Bill from: {inv_vendor}",
        "inv_sub": f"Subtotal: {money(subtotal)}",
        "limit": f"Approval limit: {money(limit)}",
    }
    po = "\n".join([
        f"PURCHASE ORDER {po_no}", lines["po_date"], lines["po_vendor"], f"Item: {item}",
        f"Qty: {qty}", lines["po_unit"], f"Freight: {money(freight)}", lines["po_total"],
    ])
    inv_1 = "\n".join([
        f"INVOICE {inv_no}", lines["inv_date"], lines["inv_vendor"], f"Reference: {po_no}",
        f"Item: {item}", f"Qty: {qty}", lines["inv_sub"],
    ])
    inv_2 = "\n".join([f"Freight: {money(freight)}", lines["inv_total"], "Terms: net 30"])
    approval = "\n".join([
        f"APPROVAL RECORD {po_no}", f"Approver: {rng.choice(APPROVERS)}", lines["limit"],
        f"Approved on: {(po_date - timedelta(days=rng.randint(0, 3))).isoformat()}",
    ])
    clean = (
        Document(f"{sid}/po", (po,)),
        Document(f"{sid}/invoice", (inv_1, inv_2)),
        Document(f"{sid}/approval", (approval,)),
    )
    anchors = {
        "po_total": Anchor("po", 1, lines["po_total"], money(po_total)),
        "po_date": Anchor("po", 1, lines["po_date"], po_date.isoformat()),
        "po_vendor": Anchor("po", 1, lines["po_vendor"], vendor),
        "invoice_total": Anchor("invoice", 2, lines["inv_total"], money(inv_total)),
        "invoice_date": Anchor("invoice", 1, lines["inv_date"], inv_date.isoformat()),
        "invoice_vendor": Anchor("invoice", 1, lines["inv_vendor"], inv_vendor),
        "approver_limit": Anchor("approval", 1, lines["limit"], money(limit)),
    }
    decoys = {
        "po_total": Anchor("po", 1, lines["po_unit"], money(unit)),
        "invoice_total": Anchor("invoice", 1, lines["inv_sub"], money(subtotal)),
    }
    truth = {a: "exception" if flags[a] else "pass" for a in ATTRIBUTES}
    return Sample(sid, clean, clean, truth, anchors, decoys)


def make_population(seed: int, n: int, exception_rate: float = 0.08) -> list[Sample]:
    rng = random.Random(f"population-{seed}")
    return [_sample(rng, i + 1, exception_rate) for i in range(n)]


def add_noise(sample: Sample, rate: float, rng: random.Random) -> Sample:
    """Swap each confusable character for another of its group with probability `rate`."""
    if rate <= 0:
        return sample

    def noisy(page: str) -> str:
        out = []
        for ch in page:
            group = _GROUP_OF.get(ch)
            if group and rng.random() < rate:
                ch = rng.choice([c for c in group if c != ch])
            out.append(ch)
        return "".join(out)

    docs = tuple(Document(d.doc_id, tuple(noisy(p) for p in d.pages)) for d in sample.clean)
    return replace(sample, docs=docs)
