"""Best-effort CloudWatch Embedded Metric Format. Never logs secrets."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from merchantos_observability.logging import get_logger
from merchantos_observability.redaction import redact_mapping

logger = get_logger(__name__)


def emit_metric(
    name: str,
    value: float,
    *,
    unit: str = "Count",
    dimensions: dict[str, str] | None = None,
) -> None:
    namespace = os.environ.get("AWS_EMF_NAMESPACE", "").strip()
    dims = redact_mapping(dict(dimensions or {}))
    payload: dict[str, Any] = {
        "metric_name": name,
        "metric_value": value,
        "metric_unit": unit,
        **{key: str(item) for key, item in dims.items()},
    }
    logger.info("metric", **payload)
    if not namespace:
        return
    emf = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [list(dims.keys())] if dims else [[]],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }
            ],
        },
        name: value,
        **dims,
    }
    print(json.dumps(emf), flush=True)
