from collections.abc import Sequence

from merchantos_domain import MAX_INTEL_AGENTS
from merchantos_mcp import AGENT_TOOLS

from merchantos_agents.registry import SPECIALIST_NAMES

AGENT_ORDER = ("analytics", "inventory", "customer")

_ANALYTICS = (
    "revenue",
    "sales",
    "aov",
    "order",
    "orders",
    "profit",
    "performance",
    "trend",
    "product",
    "products",
)
_INVENTORY = (
    "inventory",
    "stock",
    "stockout",
    "overstock",
    "units remaining",
    "sku",
    "availability",
)
_CUSTOMER = (
    "customer",
    "returning",
    "retention",
    "repeat",
    "new vs",
    "churn",
)
_BROAD = (
    "this week",
    "pay attention",
    "opportunities",
    "opportunity",
    "health",
    "what is happening",
    "what's happening",
    "biggest",
    "overview",
)
_DECLINE = ("down", "decline", "declining", "drop", "falling", "decreased")


def _has(question: str, needles: tuple[str, ...]) -> bool:
    lowered = question.lower()
    return any(item in lowered for item in needles)


def select_agents(question: str, suggested: Sequence[str] = ()) -> tuple[str, ...]:
    """Allowlisted specialist selection. Unknown names cannot be loaded."""
    chosen: set[str] = set()
    if _has(question, _BROAD):
        chosen.update(AGENT_ORDER)
    if _has(question, _ANALYTICS):
        chosen.add("analytics")
    if _has(question, _INVENTORY):
        chosen.add("inventory")
    if _has(question, _CUSTOMER):
        chosen.add("customer")
    if _has(question, ("product", "products")):
        chosen.update({"analytics", "inventory"})
    if "analytics" in chosen and _has(question, _DECLINE):
        chosen.add("inventory")
    if "customer" in chosen and (_has(question, _ANALYTICS) or _has(question, ("behavior",))):
        chosen.add("analytics")
    for name in suggested:
        if name in SPECIALIST_NAMES and name in AGENT_TOOLS:
            chosen.add(name)
    if not chosen:
        chosen.add("analytics")
    return tuple(name for name in AGENT_ORDER if name in chosen)[:MAX_INTEL_AGENTS]
