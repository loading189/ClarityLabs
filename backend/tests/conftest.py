import os
import pathlib
import sys
import tempfile

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))


def pytest_configure():
    if os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL"):
        return
    temp_dir = tempfile.mkdtemp(prefix="claritylabs-tests-")
    db_path = pathlib.Path(temp_dir) / "pytest.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"


@pytest.fixture(scope="session")
def sqlite_engine():
    from backend.app.db import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def sqlite_session(sqlite_engine):
    from backend.app.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client(sqlite_engine, sqlite_session):
    from backend.app.db import get_db
    from backend.app.main import app
    from fastapi.testclient import TestClient

    def _get_test_db():
        yield sqlite_session

    app.dependency_overrides[get_db] = _get_test_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
