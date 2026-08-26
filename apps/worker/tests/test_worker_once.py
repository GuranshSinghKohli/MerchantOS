import os

import pytest
from merchantos_worker.main import check_dependencies
from merchantos_worker.settings import WorkerSettings


@pytest.mark.integration
def test_worker_dependency_check() -> None:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is required for integration tests")
    runtime = check_dependencies(WorkerSettings(worker_once=True))
    assert runtime.queue is not None
    assert runtime.sync.reader is not None
    assert runtime.webhook.reader is not None
    assert runtime.agent.llm is not None
