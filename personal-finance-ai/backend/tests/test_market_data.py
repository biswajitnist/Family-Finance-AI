from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.finance import MarketPriceCache
from app.services import market_data_service


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeFinnhubClient:
    def __init__(self, *args, **kwargs) -> None:
        self.requests: list[tuple[str, dict]] = []

    def __enter__(self) -> "FakeFinnhubClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, path: str, params: dict) -> FakeResponse:
        self.requests.append((path, params))
        if path == "/stock/profile2":
            return FakeResponse({"currency": "USD"})
        return FakeResponse(
            {
                "c": 125.50,
                "h": 126,
                "l": 122,
                "o": 123,
                "pc": 124,
                "t": int(datetime(2026, 6, 8, 18, 30, tzinfo=timezone.utc).timestamp()),
            }
        )


class FakeMultiProviderClient:
    def __init__(self, *args, **kwargs) -> None:
        self.base_url = str(kwargs.get("base_url") or "")

    def __enter__(self) -> "FakeMultiProviderClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, path: str, params: dict) -> FakeResponse:
        if "frankfurter" in self.base_url:
            return FakeResponse({"date": "2026-06-08", "rates": {"EUR": 0.87}})
        if "twelvedata" in self.base_url:
            return FakeResponse(
                {
                    "meta": {
                        "symbol": "SXR8",
                        "currency": "EUR",
                        "exchange": "XETRA",
                    },
                    "values": [{"datetime": "2026-06-08", "close": "700.00"}],
                    "status": "ok",
                }
            )
        return FakeResponse({})


def test_market_refresh_caches_foreign_price_without_overwriting_eur_value(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "finnhub_api_key", "local-test-key")
    monkeypatch.setattr(market_data_service.httpx, "Client", FakeFinnhubClient)
    investment = client.post(
        "/api/investments",
        json={
            "asset_name": "Example Stock",
            "asset_type": "Stock",
            "ticker": "EXM",
            "quantity": "2",
            "average_price": "100",
            "currency": "USD",
            "current_value": "200",
        },
    )
    assert investment.status_code == 201

    refreshed = client.post("/api/market-data/refresh")
    assert refreshed.status_code == 200
    data = refreshed.json()
    assert data["online"] is True
    assert data["refreshed_symbols"] == ["EXM"]
    assert data["investments_updated"] == 0
    assert data["prices"][0]["price"] == "125.500000"

    saved = client.get("/api/investments").json()[0]
    assert saved["market_price"] == "125.500000"
    assert saved["market_currency"] == "USD"
    assert saved["current_value"] == "200.00"
    assert saved["quote_status"] == "fx_rate_missing"

    with SessionLocal() as db:
        intraday = db.scalar(
            select(func.count(MarketPriceCache.id)).where(
                MarketPriceCache.interval == "intraday"
            )
        )
        daily = db.scalar(
            select(func.count(MarketPriceCache.id)).where(
                MarketPriceCache.interval == "daily"
            )
        )
    assert intraday == 1
    assert daily == 1


def test_market_refresh_uses_cache_when_provider_is_unavailable(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "finnhub_api_key", "local-test-key")
    monkeypatch.setattr(market_data_service.httpx, "Client", FakeFinnhubClient)
    client.post(
        "/api/watchlist",
        json={"symbol": "AAPL", "name": "Apple", "currency": "USD"},
    )
    assert client.post("/api/market-data/refresh").json()["online"] is True

    monkeypatch.setattr(settings, "finnhub_api_key", "")
    offline = client.post("/api/market-data/refresh").json()
    assert offline["online"] is False
    assert offline["using_cache"] is True
    assert offline["status_label"] == "Offline Using Cached Data"
    assert "Showing latest cached market data" in offline["warning"]
    assert offline["prices"][0]["symbol"] == "AAPL"


def test_market_refresh_does_not_guess_currency(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "finnhub_api_key", "local-test-key")
    monkeypatch.setattr(market_data_service.httpx, "Client", FakeFinnhubClient)
    client.post(
        "/api/investments",
        json={
            "asset_name": "Euro Portfolio Stock",
            "asset_type": "Stock",
            "ticker": "EXM",
            "quantity": "2",
            "currency": "EUR",
            "current_value": "210",
        },
    )
    refreshed = client.post("/api/market-data/refresh").json()
    assert refreshed["investments_updated"] == 0
    assert "without an exchange rate" in refreshed["skipped_portfolio_updates"][0]
    saved = client.get("/api/investments").json()[0]
    assert Decimal(saved["current_value"]) == Decimal("210.00")


def test_market_refresh_settings(client: TestClient) -> None:
    response = client.put(
        "/api/market-data/settings", json={"refresh_interval": "30_minutes"}
    )
    assert response.status_code == 200
    assert response.json()["refresh_interval"] == "30_minutes"
    invalid = client.put(
        "/api/market-data/settings", json={"refresh_interval": "five_minutes"}
    )
    assert invalid.status_code == 422


def test_market_api_key_can_be_saved_locally(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    credential_path = tmp_path / "market_credentials.json"
    monkeypatch.setattr(settings, "market_credentials_file", credential_path)
    monkeypatch.setattr(settings, "finnhub_api_key", "")
    api_key = "test-local-finnhub-key-123456"

    response = client.put("/api/market-data/credentials", json={"api_key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert data["credential_source"] == "app"
    assert api_key not in response.text
    assert credential_path.exists()
    assert credential_path.stat().st_mode & 0o777 == 0o600
    assert market_data_service._api_key() == api_key

    twelve_key = "test-local-twelve-data-key-123456"
    second = client.put(
        "/api/market-data/credentials",
        json={"provider": "twelve_data", "api_key": twelve_key},
    )
    assert second.status_code == 200
    assert second.json()["providers"]["twelve_data"]["configured"] is True
    assert market_data_service._api_key("finnhub") == api_key
    assert market_data_service._api_key("twelve_data") == twelve_key
    assert twelve_key not in second.text


def test_twelve_data_refresh_updates_xetra_etf(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "finnhub_api_key", "")
    monkeypatch.setattr(settings, "twelve_data_api_key", "test-twelve-data-key-123456")
    monkeypatch.setattr(market_data_service.httpx, "Client", FakeMultiProviderClient)
    created = client.post(
        "/api/investments",
        json={
            "asset_name": "S&P 500 ETF",
            "asset_type": "ETF",
            "ticker": "SXR8",
            "provider_symbol": "SXR8.XETRA",
            "exchange": "XETRA",
            "market_provider": "Twelve Data",
            "quantity": "2",
            "average_price": "650",
            "currency": "EUR",
            "current_value": "1300",
        },
    )
    assert created.status_code == 201

    refreshed = client.post("/api/market-data/refresh").json()
    assert refreshed["online"] is True
    assert refreshed["refreshed_symbols"] == ["SXR8.XETRA"]
    saved = client.get("/api/investments").json()[0]
    assert saved["market_price"] == "700.000000"
    assert saved["market_currency"] == "EUR"
    assert saved["current_value"] == "1400.00"
    assert saved["market_data_source"] == "Twelve Data"
    assert saved["quote_status"] == "fresh"
