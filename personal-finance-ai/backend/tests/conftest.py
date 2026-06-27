import os
import shutil
from pathlib import Path

os.environ["FINANCE_DATABASE_URL"] = "sqlite:///./test_finance.db"
os.environ["FINANCE_UPLOADS_DIR"] = "./test_artifacts/uploads"
os.environ["FINANCE_PROCESSED_DIR"] = "./test_artifacts/processed"
os.environ["FINANCE_REPORTS_DIR"] = "./test_artifacts/reports"
os.environ["FINANCE_CHROMA_DIR"] = "./test_artifacts/chroma"
os.environ["FINANCE_MARKET_CREDENTIALS_FILE"] = (
    "./test_artifacts/market_credentials.json"
)

import pytest
from fastapi.testclient import TestClient

from app.db.init_db import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database() -> None:
    engine.dispose()
    Path("test_finance.db").unlink(missing_ok=True)
    for directory in ("uploads", "processed", "reports"):
        shutil.rmtree(Path("test_artifacts") / directory, ignore_errors=True)
    Path("test_artifacts/market_credentials.json").unlink(missing_ok=True)
    Path("test_artifacts/provider_secret.key").unlink(missing_ok=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    Path("test_finance.db").unlink(missing_ok=True)
    for directory in ("uploads", "processed", "reports"):
        shutil.rmtree(Path("test_artifacts") / directory, ignore_errors=True)
    Path("test_artifacts/market_credentials.json").unlink(missing_ok=True)
    Path("test_artifacts/provider_secret.key").unlink(missing_ok=True)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
