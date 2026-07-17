"""Fleet service live E2E fixtures (shared Cognito scratch users)."""
from __future__ import annotations

from typing import Iterator

import pytest

from tests_e2e.helpers import scratch_user


@pytest.fixture
def operator_token() -> Iterator[str]:
    for user in scratch_user(operator=True):
        yield user.access_token
