from __future__ import annotations

import re
from typing import Any

from merchantos_domain import (
    MAX_EVIDENCE_ITEMS,
    ClaimKind,
    ConfidenceBand,
    EvidenceItem,
    Finding,
)

from merchantos_agents.state import ToolResult

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_BAND_ORDER = {
    ConfidenceBand.LOW: 0,
    ConfidenceBand.MEDIUM: 1,
    ConfidenceBand.HIGH: 2,
}
_KPI_KEYS = ("revenue", "orders", "aov", "customers", "new_customers", "returning_customers")
_GROWTH_KEYS = ("revenue", "orders", "aov", "customers")
_PREV_KEYS = ("revenue", "orders", "aov", "customers")
_INV_KEYS = (
    "tracked_variants",
    "in_stock_variants",
    "out_of_stock_variants",
    "available_units",
    "on_hand_units",
    "utilization_pct",
)


def redact_untrusted_text(value: str) -> str:
    return _EMAIL.sub("[redacted]", value)


def redact_untrusted_payload(value: Any) -> Any:
    if isinstance(value, str):
        return redact_untrusted_text(value)
    if isinstance(value, dict):
        return {key: redact_untrusted_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_untrusted_payload(item) for item in value]
    return value


def _text(value: object, *, merchant: bool = False) -> str:
    raw = " ".join(str(value).split())
    if _EMAIL.search(raw):
        return "[redacted]"
    clipped = raw[:180]
    if merchant:
        return f"merchant_text:{clipped}"
    return clipped


def _walk_kpis(source: str, kpis: dict[str, Any], facts: list[tuple[str, str]]) -> None:
    for key in _KPI_KEYS:
        if kpis.get(key) is not None:
            facts.append((source, f"{key}={kpis[key]}"))
    previous = kpis.get("previous")
    if isinstance(previous, dict):
        for key in _PREV_KEYS:
            if previous.get(key) is not None:
                facts.append((source, f"previous_{key}={previous[key]}"))
    growth = kpis.get("growth_pct")
    if isinstance(growth, dict):
        for key in _GROWTH_KEYS:
            if growth.get(key) is not None:
                facts.append((source, f"{key}_growth_pct={growth[key]}"))


def extract_evidence(results: list[ToolResult]) -> list[EvidenceItem]:
    """Deterministic facts from tool output. The LLM is not the calculator."""
    facts: list[tuple[str, str]] = []
    for result in results:
        if not result.ok:
            facts.append((result.name, f"tool_error={result.error_code or 'error'}"))
            continue
        output = result.output
        source = result.name
        window = output.get("range")
        if isinstance(window, dict):
            current = window.get("current")
            if isinstance(current, dict):
                start = current.get("start_local") or current.get("start")
                end = current.get("end_local_exclusive") or current.get("end")
                if start and end:
                    facts.append((source, f"date_range={start}/{end}"))
                if current.get("preset"):
                    facts.append((source, f"preset={current['preset']}"))
        kpis = output.get("kpis")
        if isinstance(kpis, dict):
            _walk_kpis(source, kpis, facts)
        if output.get("orders") is not None and not isinstance(output.get("orders"), dict):
            facts.append((source, f"orders={output['orders']}"))
        if output.get("previous_orders") is not None:
            facts.append((source, f"previous_orders={output['previous_orders']}"))
        if output.get("growth_pct") is not None and not isinstance(output.get("growth_pct"), dict):
            facts.append((source, f"orders_growth_pct={output['growth_pct']}"))
        health = output.get("health")
        if isinstance(health, dict) and health.get("status") is not None:
            facts.append((source, f"health_status={health['status']}"))
        inventory = output.get("inventory")
        if isinstance(inventory, dict):
            for key in _INV_KEYS:
                if inventory.get(key) is not None:
                    facts.append((source, f"{key}={inventory[key]}"))
        items = output.get("items") or output.get("products")
        if isinstance(items, list):
            for index, item in enumerate(items[:5]):
                if not isinstance(item, dict):
                    continue
                title = _text(item.get("title") or item.get("product_gid") or index, merchant=True)
                parts = [f"product[{index}]={title}"]
                if item.get("revenue") is not None:
                    parts.append(f"revenue={item['revenue']}")
                if item.get("units_sold") is not None:
                    parts.append(f"units_sold={item['units_sold']}")
                if item.get("available") is not None:
                    parts.append(f"available={item['available']}")
                facts.append((source, "; ".join(parts)))
            if output.get("total") is not None:
                facts.append((source, f"product_rows={output['total']}"))
        trend = output.get("trend") or output.get("revenue")
        if isinstance(trend, list) and not trend:
            facts.append((source, "trend_empty=true"))
    unique: list[EvidenceItem] = []
    seen_pairs: set[str] = set()
    seen_values: dict[str, set[str]] = {}
    for source, fact in facts:
        pair = f"{source}:{fact}"
        if pair in seen_pairs:
            continue
        metric, sep, raw = fact.partition("=")
        if sep and raw in seen_values.get(metric, set()):
            continue
        seen_pairs.add(pair)
        if sep:
            seen_values.setdefault(metric, set()).add(raw)
        unique.append(
            EvidenceItem(id=f"ev_{len(unique) + 1}", source=source, fact=_text(fact)[:500])
        )
        if len(unique) >= MAX_EVIDENCE_ITEMS:
            break
    return unique


def has_conflicting_evidence(evidence: list[EvidenceItem]) -> bool:
    signs: dict[str, set[str]] = {}
    for item in evidence:
        if "_growth_pct=" not in item.fact:
            continue
        metric, _, raw = item.fact.partition("=")
        try:
            value = float(raw)
        except ValueError:
            continue
        if value == 0:
            continue
        signs.setdefault(metric, set()).add("pos" if value > 0 else "neg")
    return any("pos" in buckets and "neg" in buckets for buckets in signs.values())


def ground_findings(
    drafts: list[Finding],
    evidence: list[EvidenceItem],
) -> tuple[list[Finding], list[str]]:
    known = {item.id for item in evidence if item.id}
    grounded: list[Finding] = []
    limitations: list[str] = []
    for draft in drafts:
        valid = [ref for ref in draft.evidence_ids if ref in known]
        if not valid:
            limitations.append(f"dropped ungrounded finding: {draft.title[:80]}")
            continue
        grounded.append(draft.model_copy(update={"evidence_ids": valid}))
    return grounded, limitations


def resolve_confidence(
    *,
    evidence: list[EvidenceItem],
    findings: list[Finding],
    tool_errors: bool,
    insufficient: bool,
    conflicting: bool,
    proposed: ConfidenceBand,
    assumptions: list[str],
) -> ConfidenceBand:
    """Deterministic ceiling. The model may only stay or go lower."""
    ceiling = ConfidenceBand.HIGH
    kinds = {item.claim_kind for item in findings}
    if (
        insufficient
        or not evidence
        or tool_errors
        or conflicting
        or (findings and kinds <= {ClaimKind.HYPOTHESIS})
        or any(item.fact.startswith("tool_error=") for item in evidence)
    ):
        ceiling = ConfidenceBand.LOW
    elif (
        assumptions
        or ClaimKind.INFERENCE in kinds
        or ClaimKind.HYPOTHESIS in kinds
        or len(evidence) < 2
        or not findings
    ):
        ceiling = ConfidenceBand.MEDIUM
    if _BAND_ORDER[proposed] < _BAND_ORDER[ceiling]:
        return proposed
    return ceiling
