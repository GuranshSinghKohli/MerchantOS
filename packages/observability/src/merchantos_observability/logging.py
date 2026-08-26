import logging
from collections.abc import MutableMapping
from typing import Any, TextIO, cast

import structlog

from merchantos_observability.redaction import redact_mapping


def _redact_event(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    redacted = redact_mapping(dict(event_dict))
    event_dict.clear()
    event_dict.update(redacted)
    return event_dict


def configure_logging(*, level: str = "INFO", stream: TextIO | None = None) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s", stream=stream, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_event,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        context_class=dict,
        logger_factory=(
            structlog.PrintLoggerFactory(file=stream) if stream else structlog.PrintLoggerFactory()
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def bind_request_id(request_id: str) -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
