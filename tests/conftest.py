"""
Shared test setup: build the sample database once before tests that need it.
"""

import pytest

from scripts.create_database import create_database
from src.config import DB_PATH


@pytest.fixture(scope="session", autouse=True)
def sample_database():
    if not DB_PATH.exists():
        create_database(DB_PATH)
    return DB_PATH
