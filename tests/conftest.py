import pytest

from tests.fakes import FakeSleep


@pytest.fixture
def sleep() -> FakeSleep:
    return FakeSleep()
