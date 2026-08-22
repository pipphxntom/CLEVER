import pytest

from gateway import catalog


@pytest.fixture(autouse=True)
def _reload_catalog():
    catalog.reload()
    yield
