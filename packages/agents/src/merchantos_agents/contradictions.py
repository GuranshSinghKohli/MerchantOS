from merchantos_domain import Contradiction, EvidenceItem


def detect_contradictions(evidence: list[EvidenceItem]) -> list[Contradiction]:
    """Prefer deterministic metric signs over model judgment."""
    by_metric: dict[str, list[EvidenceItem]] = {}
    for item in evidence:
        if "=" not in item.fact:
            continue
        metric, _, raw = item.fact.partition("=")
        if not metric.endswith("_growth_pct"):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value == 0:
            continue
        by_metric.setdefault(metric, []).append(item)
    found: list[Contradiction] = []
    for metric, items in by_metric.items():
        positives = [item for item in items if float(item.fact.partition("=")[2]) > 0]
        negatives = [item for item in items if float(item.fact.partition("=")[2]) < 0]
        if not positives or not negatives:
            continue
        found.append(
            Contradiction(
                id=f"cx_{len(found) + 1}",
                metric=metric,
                left_source=positives[0].source,
                left_fact=positives[0].fact,
                right_source=negatives[0].source,
                right_fact=negatives[0].fact,
                status="unresolved",
            )
        )
        if len(found) >= 8:
            break
    return found
