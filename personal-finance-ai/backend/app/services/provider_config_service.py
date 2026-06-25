from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.finance import MarketDataProvider

APPROVED_MARKET_HOSTS = {
    "finnhub.io",
    "api.finnhub.io",
    "api.twelvedata.com",
    "query1.finance.yahoo.com",
    "www.alphavantage.co",
    "api.mfapi.in",
    "api.openfigi.com",
    "api.frankfurter.dev",
}
def _secret() -> bytes:
    secret_file = settings.market_credentials_file.with_name(
        "provider_secret.key"
    )
    if secret_file.exists():
        return secret_file.read_bytes()
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    value = os.urandom(32)
    secret_file.write_bytes(value)
    os.chmod(secret_file, 0o600)
    return value


def encrypt_api_key(value: str) -> str:
    plaintext = value.strip().encode()
    nonce = os.urandom(16)
    secret = _secret()
    stream = b""
    counter = 0
    while len(stream) < len(plaintext):
        stream += hashlib.sha256(
            secret + nonce + counter.to_bytes(4, "big")
        ).digest()
        counter += 1
    ciphertext = bytes(
        left ^ right for left, right in zip(plaintext, stream, strict=False)
    )
    signature = hmac.new(secret, nonce + ciphertext, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + signature + ciphertext).decode()


def decrypt_api_key(value: str | None) -> str:
    if not value:
        return ""
    payload = base64.urlsafe_b64decode(value.encode())
    nonce, signature, ciphertext = payload[:16], payload[16:48], payload[48:]
    secret = _secret()
    expected = hmac.new(secret, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Stored API credential could not be verified")
    stream = b""
    counter = 0
    while len(stream) < len(ciphertext):
        stream += hashlib.sha256(
            secret + nonce + counter.to_bytes(4, "big")
        ).digest()
        counter += 1
    return bytes(
        left ^ right for left, right in zip(ciphertext, stream, strict=False)
    ).decode()


def provider_read(provider: MarketDataProvider) -> dict:
    key = decrypt_api_key(provider.api_key_encrypted)
    masked = None
    if key:
        masked = (
            f"{key[:3]}{'*' * max(8, len(key) - 6)}{key[-3:]}"
            if len(key) > 6
            else "********"
        )
    return {
        column.name: getattr(provider, column.name)
        for column in provider.__table__.columns
        if column.name not in {"api_key_encrypted"}
    } | {"api_key_masked": masked, "has_api_key": bool(key)}


def _approved_url(value: str | None) -> str:
    if not value:
        raise ValueError("Base URL is required")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in APPROVED_MARKET_HOSTS:
        raise ValueError("Provider URL is not on the approved market-data list")
    return value.rstrip("/")


def _auth(
    provider: MarketDataProvider,
    api_key: str,
) -> tuple[dict[str, str], dict[str, str]]:
    headers: dict[str, str] = {}
    params: dict[str, str] = {}
    if not api_key:
        return headers, params
    if provider.auth_method == "API Key in Query Parameter":
        params[provider.api_key_parameter_name or "apikey"] = api_key
    elif provider.auth_method == "API Key in Header":
        headers[provider.api_key_header_name or "X-API-Key"] = api_key
    elif provider.auth_method == "Bearer Token":
        headers["Authorization"] = f"Bearer {api_key}"
    return headers, params


def test_provider(db: Session, provider: MarketDataProvider) -> dict:
    started = datetime.now(timezone.utc)
    try:
        base_url = _approved_url(provider.base_url)
        api_key = decrypt_api_key(provider.api_key_encrypted)
        headers, auth_params = _auth(provider, api_key)
        name = provider.provider_name.casefold()
        symbol = provider.test_symbol or "NVDA"
        path = ""
        params = dict(auth_params)
        if "finnhub" in name:
            path = "/quote"
            params["symbol"] = symbol
        elif "twelve" in name:
            path = "/price"
            params["symbol"] = symbol
            if provider.default_exchange_code:
                params["exchange"] = provider.default_exchange_code
        elif "yahoo" in name or "yfinance" in name:
            path = f"/v8/finance/chart/{symbol}"
        elif "alpha" in name:
            params |= {"function": "GLOBAL_QUOTE", "symbol": symbol}
        elif "mfapi" in name:
            path = "/mf/search"
            params["q"] = symbol
        elif provider.provider_type.casefold() == "fx":
            path = "/latest"
            params |= {"base": "EUR", "symbols": "USD"}
        with httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=provider.timeout_seconds,
        ) as client:
            response = client.get(path or "/", params=params)
            response.raise_for_status()
            if not response.content:
                raise ValueError("Provider returned an empty response")
        provider.last_test_status = "online"
        provider.last_error = None
    except (httpx.HTTPError, OSError, ValueError, TypeError) as error:
        provider.last_test_status = "failed"
        provider.last_error = str(error)[:500]
    provider.last_tested_at = started
    db.commit()
    db.refresh(provider)
    return provider_read(provider)


def seed_market_providers(db: Session) -> None:
    defaults = [
        {
            "provider_name": "Finnhub",
            "provider_type": "Stock",
            "base_url": "https://finnhub.io/api/v1",
            "auth_method": "API Key in Query Parameter",
            "api_key_parameter_name": "token",
            "supported_asset_classes": "Stock",
            "default_currency": "USD",
            "test_symbol": "NVDA",
            "priority": 10,
        },
        {
            "provider_name": "Yahoo Finance",
            "provider_type": "Stock, ETF",
            "base_url": "https://query1.finance.yahoo.com",
            "auth_method": "None",
            "supported_asset_classes": "Stock,ETF",
            "test_symbol": "SXR8.DE",
            "priority": 20,
        },
        {
            "provider_name": "Twelve Data",
            "provider_type": "ETF, Stock",
            "base_url": "https://api.twelvedata.com",
            "auth_method": "API Key in Query Parameter",
            "api_key_parameter_name": "apikey",
            "supported_asset_classes": "ETF,Stock",
            "default_exchange_code": "XETR",
            "test_symbol": "SXR8",
            "priority": 30,
        },
        {
            "provider_name": "Alpha Vantage",
            "provider_type": "Stock, ETF, FX",
            "base_url": "https://www.alphavantage.co/query",
            "auth_method": "API Key in Query Parameter",
            "api_key_parameter_name": "apikey",
            "supported_asset_classes": "Stock,ETF,FX",
            "test_symbol": "GOOGL",
            "priority": 40,
        },
        {
            "provider_name": "MFAPI",
            "provider_type": "Mutual Fund",
            "base_url": "https://api.mfapi.in",
            "auth_method": "None",
            "supported_asset_classes": "Mutual Fund",
            "default_currency": "INR",
            "test_symbol": "Parag Parikh",
            "priority": 10,
        },
        {
            "provider_name": "OpenFIGI",
            "provider_type": "ISIN Mapping",
            "base_url": "https://api.openfigi.com/v3",
            "auth_method": "API Key in Header",
            "api_key_header_name": "X-OPENFIGI-APIKEY",
            "test_symbol": "IE00B5BMR087",
            "priority": 50,
        },
        {
            "provider_name": "Frankfurter FX",
            "provider_type": "FX",
            "base_url": "https://api.frankfurter.dev/v1",
            "auth_method": "None",
            "supported_asset_classes": "FX",
            "test_symbol": "EUR/USD",
            "priority": 10,
        },
    ]
    existing = set(db.scalars(select(MarketDataProvider.provider_name)).all())
    for values in defaults:
        if values["provider_name"] not in existing:
            db.add(MarketDataProvider(**values))
    db.commit()
    legacy_file = settings.market_credentials_file
    try:
        legacy = json.loads(legacy_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        legacy = {}
    legacy_keys = {
        "Finnhub": str(legacy.get("finnhub_api_key") or "").strip(),
        "Twelve Data": str(legacy.get("twelve_data_api_key") or "").strip(),
    }
    for provider_name, api_key in legacy_keys.items():
        if not api_key:
            continue
        provider = db.scalar(
            select(MarketDataProvider).where(
                MarketDataProvider.provider_name == provider_name
            )
        )
        if provider and not provider.api_key_encrypted:
            provider.api_key_encrypted = encrypt_api_key(api_key)
    db.commit()
