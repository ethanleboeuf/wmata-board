from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).parents[1]


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
