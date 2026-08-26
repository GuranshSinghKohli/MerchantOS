from merchantos_domain import JobKind, QueueMessage, TransientJobError
from merchantos_observability import get_logger

from merchantos_worker.capabilities import WorkerRuntime
from merchantos_worker.handlers import handle_agent_run, handle_sync, handle_webhook
from merchantos_worker.publisher import publish_unpublished

logger = get_logger(__name__)


def process_once(runtime: WorkerRuntime, *, wait_seconds: int = 0) -> int:
    publish_unpublished(runtime.engine, runtime.queue)
    received = runtime.queue.receive(
        max_messages=5, wait_seconds=wait_seconds, visibility_timeout=60
    )
    handled = 0
    for item in received:
        try:
            dispatch(runtime, item.message)
            runtime.queue.delete(item.receipt_handle)
            handled += 1
        except TransientJobError:
            runtime.queue.nack(item.receipt_handle)
            logger.warning(
                "job_retry", job_id=str(item.message.job_id), job_kind=item.message.job_kind
            )
        except Exception:
            logger.warning(
                "job_failed",
                job_id=str(item.message.job_id),
                job_kind=item.message.job_kind,
                error_type="unexpected",
            )
            runtime.queue.nack(item.receipt_handle)
    return handled


def dispatch(runtime: WorkerRuntime, message: QueueMessage) -> None:
    if message.job_kind == JobKind.SYNC:
        handle_sync(
            engine=runtime.engine,
            reader=runtime.sync.reader,
            encryptor=runtime.encryptor,
            job_id=message.job_id,
            owner=runtime.owner,
        )
        return
    if message.job_kind == JobKind.WEBHOOK:
        handle_webhook(
            engine=runtime.engine,
            reader=runtime.webhook.reader,
            encryptor=runtime.encryptor,
            job_id=message.job_id,
        )
        return
    if message.job_kind == JobKind.AGENT_RUN:
        handle_agent_run(
            engine=runtime.engine,
            caps=runtime.agent,
            job_id=message.job_id,
            owner=runtime.owner,
        )
        return
    logger.info("job_ignored", job_kind=message.job_kind, job_id=str(message.job_id))
