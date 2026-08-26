import os

import pytest
from merchantos_worker.main import check_dependencies
from merchantos_worker.settings import WorkerSettings


@pytest.mark.integration
def test_worker_dependency_check() -> None:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is required for integration tests")
    capabilities = check_dependencies(WorkerSettings(worker_once=True))
    assert capabilities.queue is not None
