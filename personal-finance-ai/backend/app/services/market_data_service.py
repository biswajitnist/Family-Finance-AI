from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.finance import (
    FxRate,
    Investment,
    MarketDataPreference,
    MarketPriceCache,
    WatchlistItem,
)
from app.services.currency_service import base_currency, latest_rate

PROVIDER = "Finnhub"
ALLOWED_PROVIDER_HOSTS = {"finnhub.io", "api.finnhub.io"}
TWELVE_DATA_PROVIDER = "Twelve Data"
ALLOWED_TWELVE_DATA_HOSTS = {"api.twelvedata.com"}
ALLOWED_FX_HOSTS = {"api.frankfurter.dev"}
REFRESH_INTERVALS = {
    "manual": None,
    "15_minutes": timedelta(minutes=15),
    "30_minutes": timedelta(minutes=30),
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
}


def _stored_credentials() -> dict[str, str]:
    try:
        payload = json.loads(
            settings.market_credentials_file.read_text(encoding="utf-8")
        )
        return {
            "finnhub": str(payload.get("finnhub_api_key") or "").strip(),
            "twelve_data": str(payload.get("twelve_data_api_key") or "").strip(),
        }
    except (FileNotFoundError, OSError, ValueError, AttributeError):
        return {"finnhub": "", "twelve_data": ""}


def _api_key(provider: str = "finnhub") -> str:
    stored = _stored_credentials()
    if provider == "twelve_data":
        return stored["twelve_data"] or settings.twelve_data_api_key.strip()
    return stored["finnhub"] or settings.finnhub_api_key.strip()


def save_market_api_key(db: Session, api_key: str, provider: str = "finnhub") -> None:
    value = api_key.strip()
    if len(value) < 16:
        raise ValueError("API key is too short")
    if provider not in {"finnhub", "twelve_data"}:
        raise ValueError("Unsupported market data provider")
    path = settings.market_credentials_file
    path.parent.mkdir(parents=True, exist_ok=True)
    credentials = _stored_credentials()
    credentials[provider] = value
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "finnhub_api_key": credentials["finnhub"],
                "twelve_data_api_key": credentials["twelve_data"],
            }
        ),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
    from app.models.finance import MarketDataProvider
    from app.services.provider_config_service import encrypt_api_key

    provider_name = "Finnhub" if provider == "finnhub" else "Twelve Data"
    configured_provider = db.scalar(
        select(MarketDataProvider).where(
            MarketDataProvider.provider_name == provider_name
        )
    )
    if configured_provider:
        configured_provider.api_key_encrypted = encrypt_api_key(value)
    preference = _preference(db)
    if preference.last_error == "Finnhub API key is not configured.":
        preference.last_status = "not_refreshed"
        preference.last_error = None
    db.commit()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _preference(db: Session) -> MarketDataPreference:
    item = db.scalar(
        select(MarketDataPreference).where(MarketDataPreference.user_id == 1)
    )
    if item is None:
        item = MarketDataPreference(user_id=1)
        db.add(item)
        db.flush()
    return item


def _provider_url() -> str:
    parsed = urlparse(settings.finnhub_base_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_PROVIDER_HOSTS:
        raise RuntimeError("Market data provider URL is not approved")
    return settings.finnhub_base_url.rstrip("/")


def _twelve_data_url() -> str:
    parsed = urlparse(settings.twelve_data_base_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_TWELVE_DATA_HOSTS:
        raise RuntimeError("Twelve Data provider URL is not approved")
    return settings.twelve_data_base_url.rstrip("/")


def _fx_provider_url() -> str:
    parsed = urlparse(settings.fx_base_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_FX_HOSTS:
        raise RuntimeError("FX provider URL is not approved")
    return settings.fx_base_url.rstrip("/")


def _latest_fx_rate(db: Session, from_currency: str, to_currency: str) -> FxRate | None:
    return db.scalar(
        select(FxRate)
        .where(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
        )
        .order_by(FxRate.rate_date.desc(), FxRate.created_at.desc())
    )


def _refresh_fx_rate(
    db: Session, from_currency: str, to_currency: str
) -> tuple[Decimal | None, bool]:
    if from_currency == to_currency:
        return Decimal("1"), True
    try:
        with httpx.Client(
            base_url=_fx_provider_url(),
            timeout=settings.market_data_timeout_seconds,
        ) as client:
            response = client.get(
                "/latest", params={"base": from_currency, "symbols": to_currency}
            )
            response.raise_for_status()
            payload = response.json()
            rate = _decimal((payload.get("rates") or {}).get(to_currency))
            if rate <= 0:
                raise ValueError(
                    f"{from_currency} to {to_currency} rate is unavailable"
                )
            rate_date = date.fromisoformat(str(payload.get("date")))
            existing = db.scalar(
                select(FxRate).where(
                    FxRate.from_currency == from_currency,
                    FxRate.to_currency == to_currency,
                    FxRate.rate_date == rate_date,
                )
            )
            if existing is None:
                db.add(
                    FxRate(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        rate=rate,
                        provider="Frankfurter",
                        rate_date=rate_date,
                    )
                )
            else:
                existing.rate = rate
                existing.provider = "Frankfurter"
            return rate, True
    except (httpx.HTTPError, RuntimeError, OSError, ValueError, TypeError):
        return latest_rate(db, from_currency, to_currency), False


def _indian_native_value(item: Investment) -> Decimal:
    if item.native_value and item.native_value > 0:
        return item.native_value
    if item.market_currency == "INR" and item.market_price and item.quantity > 0:
        return item.market_price * item.quantity
    if item.quantity > 0 and item.average_price > 0:
        return item.quantity * item.average_price
    if item.current_value > 1000:
        return item.current_value
    return Decimal("0")


def _convert_indian_investments(
    db: Session,
    rate: Decimal | None,
    reporting_currency: str,
) -> int:
    if not rate:
        return 0
    updated = 0
    items = db.scalars(
        select(Investment).where(Investment.purchase_currency == "INR")
    ).all()
    for item in items:
        native_value = _indian_native_value(item)
        if native_value <= 0:
            item.quote_status = "native_value_missing"
            continue
        item.native_value = native_value.quantize(Decimal("0.01"))
        item.fx_rate_to_eur = rate
        item.current_value = (native_value * rate).quantize(Decimal("0.01"))
        item.base_currency = reporting_currency
        item.currency = reporting_currency
        item.quote_status = "fresh"
        updated += 1
    return updated


def investment_values_in_base(db: Session, payload: dict) -> dict:
    reporting_currency = base_currency(db)
    purchase_currency = str(
        payload.get("purchase_currency") or reporting_currency
    ).upper()
    current_value = _decimal(payload.get("current_value"))
    native_value = _decimal(payload.get("native_value"))
    if native_value <= 0 and current_value <= 0:
        quantity = _decimal(payload.get("quantity"))
        average_price = _decimal(payload.get("average_price"))
        native_value = quantity * average_price
    rate = latest_rate(db, purchase_currency, reporting_currency)
    if native_value > 0:
        payload["native_value"] = native_value.quantize(Decimal("0.01"))
    if current_value <= 0 and native_value > 0 and rate:
        payload["current_value"] = (native_value * rate).quantize(
            Decimal("0.01")
        )
    payload["currency"] = reporting_currency
    payload["base_currency"] = reporting_currency
    return payload


def _symbols(db: Session) -> list[str]:
    investment_symbols = db.scalars(
        select(func.coalesce(Investment.provider_symbol, Investment.ticker)).where(
            Investment.ticker.is_not(None),
            Investment.ticker != "",
            (Investment.market_provider.is_(None))
            | (func.lower(Investment.market_provider) == "finnhub"),
        )
    ).all()
    watchlist_symbols = db.scalars(select(WatchlistItem.symbol)).all()
    return sorted(
        {
            str(symbol).strip().upper()
            for symbol in [*investment_symbols, *watchlist_symbols]
            if symbol
        }
    )


def _twelve_data_investments(db: Session) -> list[Investment]:
    return list(
        db.scalars(
            select(Investment).where(
                func.lower(Investment.market_provider) == "twelve data",
                Investment.ticker.is_not(None),
                Investment.ticker != "",
            )
        ).all()
    )


def _latest_prices(db: Session) -> list[dict]:
    rows = db.execute(
        select(MarketPriceCache)
        .where(MarketPriceCache.interval == "intraday")
        .order_by(MarketPriceCache.symbol, MarketPriceCache.fetched_at.desc())
    ).scalars()
    latest: dict[str, MarketPriceCache] = {}
    for row in rows:
        latest.setdefault(row.symbol, row)
    return [
        {
            "symbol": row.symbol,
            "price": row.price,
            "currency": row.currency,
            "quote_timestamp": row.quote_timestamp,
            "fetched_at": row.fetched_at,
            "provider": row.provider,
        }
        for row in latest.values()
    ]


def market_data_status(db: Session) -> dict:
    preference = _preference(db)
    finnhub_symbols = _symbols(db)
    twelve_items = _twelve_data_investments(db)
    symbols = sorted(
        {
            *finnhub_symbols,
            *[
                str(item.provider_symbol or item.ticker).upper()
                for item in twelve_items
            ],
        }
    )
    latest = _latest_prices(db)
    last_success = _as_aware(preference.last_success_at)
    interval = REFRESH_INTERVALS.get(preference.refresh_interval)
    next_refresh = last_success + interval if last_success and interval else None
    refresh_due = bool(interval and (last_success is None or _utcnow() >= next_refresh))
    stored = _stored_credentials()
    finnhub_configured = bool(stored["finnhub"] or settings.finnhub_api_key)
    twelve_configured = bool(stored["twelve_data"] or settings.twelve_data_api_key)
    configured = finnhub_configured or twelve_configured
    provider_online = preference.last_status in {"online", "online_partial"}
    using_cache = not provider_online and bool(latest)
    if preference.last_status == "online":
        label = "Online"
    elif preference.last_status == "online_partial":
        label = "Online (Partial)"
    elif using_cache:
        label = "Offline Using Cached Data"
    elif not configured:
        label = "API Key Required"
    else:
        label = "Not Refreshed"
    warning = preference.last_error
    if using_cache and last_success:
        warning = (
            "Internet connection unavailable. Showing latest cached market data "
            f"from {last_success.strftime('%d-%b-%Y %H:%M')}."
        )
    return {
        "provider": PROVIDER,
        "configured": configured,
        "credential_source": (
            "app"
            if any(stored.values())
            else "environment"
            if settings.finnhub_api_key or settings.twelve_data_api_key
            else None
        ),
        "providers": {
            "finnhub": {
                "configured": finnhub_configured,
                "credential_source": (
                    "app"
                    if stored["finnhub"]
                    else "environment"
                    if settings.finnhub_api_key
                    else None
                ),
            },
            "twelve_data": {
                "configured": twelve_configured,
                "credential_source": (
                    "app"
                    if stored["twelve_data"]
                    else "environment"
                    if settings.twelve_data_api_key
                    else None
                ),
                "tracked_symbols": len(twelve_items),
            },
        },
        "status": preference.last_status,
        "status_label": label,
        "online": provider_online,
        "using_cache": using_cache,
        "last_updated": preference.last_success_at,
        "last_attempt": preference.last_attempt_at,
        "last_error": preference.last_error,
        "warning": warning,
        "refresh_interval": preference.refresh_interval,
        "next_refresh": next_refresh,
        "refresh_due": refresh_due,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "missing_ticker_count": db.scalar(
            select(func.count(Investment.id)).where(
                ((Investment.ticker.is_(None)) | (Investment.ticker == "")),
                (Investment.market_provider.is_(None))
                | (func.lower(Investment.market_provider) != "mfapi"),
            )
        )
        or 0,
        "prices": latest,
        "cache_policy": {
            "intraday_days": 7,
            "daily_retention": "unlimited",
            "news_days": 30,
        },
    }


def update_market_settings(db: Session, refresh_interval: str) -> dict:
    if refresh_interval not in REFRESH_INTERVALS:
        raise ValueError("Invalid market data refresh interval")
    preference = _preference(db)
    preference.refresh_interval = refresh_interval
    db.commit()
    return market_data_status(db)


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _profile_currency(client: httpx.Client, symbol: str) -> str | None:
    try:
        response = client.get("/stock/profile2", params={"symbol": symbol})
        response.raise_for_status()
        currency = response.json().get("currency")
        return str(currency).upper()[:3] if currency else None
    except (httpx.HTTPError, ValueError, AttributeError):
        return None


def _store_quote(
    db: Session,
    symbol: str,
    price: Decimal,
    currency: str | None,
    quote_time: datetime,
    fetched_at: datetime,
    provider: str = PROVIDER,
) -> None:
    existing_intraday = db.scalar(
        select(MarketPriceCache).where(
            MarketPriceCache.symbol == symbol,
            MarketPriceCache.provider == provider,
            MarketPriceCache.interval == "intraday",
            MarketPriceCache.quote_timestamp == quote_time,
        )
    )
    if existing_intraday is None:
        db.add(
            MarketPriceCache(
                symbol=symbol,
                provider=provider,
                price=price,
                currency=currency,
                interval="intraday",
                quote_timestamp=quote_time,
                fetched_at=fetched_at,
            )
        )
    else:
        existing_intraday.price = price
        existing_intraday.currency = currency
        existing_intraday.fetched_at = fetched_at
    daily_time = quote_time.replace(hour=0, minute=0, second=0, microsecond=0)
    existing_daily = db.scalar(
        select(MarketPriceCache).where(
            MarketPriceCache.symbol == symbol,
            MarketPriceCache.provider == provider,
            MarketPriceCache.interval == "daily",
            MarketPriceCache.quote_timestamp == daily_time,
        )
    )
    if existing_daily is None:
        db.add(
            MarketPriceCache(
                symbol=symbol,
                provider=provider,
                price=price,
                currency=currency,
                interval="daily",
                quote_timestamp=daily_time,
                fetched_at=fetched_at,
            )
        )
    else:
        existing_daily.price = price
        existing_daily.currency = currency
        existing_daily.fetched_at = fetched_at


def _update_investments(
    db: Session,
    symbol: str,
    price: Decimal,
    currency: str | None,
    fetched_at: datetime,
    fx_rates: dict[str, Decimal | None] | None = None,
    provider: str = PROVIDER,
) -> tuple[int, list[str]]:
    updated = 0
    skipped: list[str] = []
    investments = db.scalars(
        select(Investment).where(
            func.upper(func.coalesce(Investment.provider_symbol, Investment.ticker))
            == symbol
        )
    ).all()
    reporting_currency = base_currency(db)
    for item in investments:
        item.market_price = price
        item.market_currency = currency
        item.market_price_updated_at = fetched_at
        item.market_data_source = provider
        item.market_provider = item.market_provider or provider
        if item.quantity <= 0:
            item.quote_status = "quantity_missing"
            skipped.append(f"{item.asset_name}: quantity is missing")
            continue
        if not currency:
            item.quote_status = "currency_missing"
            skipped.append(f"{item.asset_name}: market currency is unavailable")
            continue
        if currency == reporting_currency:
            item.fx_rate_to_eur = Decimal("1")
            item.price_eur = price
            item.current_value = (item.quantity * price).quantize(Decimal("0.01"))
            item.base_currency = reporting_currency
            item.currency = reporting_currency
            item.quote_status = "fresh"
            updated += 1
            continue
        direct_rate = (fx_rates or {}).get(currency)
        stored_rate = (
            _latest_fx_rate(db, currency, reporting_currency)
            if not direct_rate
            else None
        )
        rate = direct_rate or (stored_rate.rate if stored_rate else None)
        if rate:
            item.fx_rate_to_eur = rate
            item.price_eur = (price * rate).quantize(Decimal("0.000001"))
            item.current_value = (item.quantity * item.price_eur).quantize(
                Decimal("0.01")
            )
            item.base_currency = reporting_currency
            item.currency = reporting_currency
            item.quote_status = "fresh"
            updated += 1
            continue
        item.quote_status = "fx_rate_missing"
        if item.base_currency.upper() != reporting_currency:
            item.base_currency = reporting_currency
        if item.currency.upper() != currency:
            skipped.append(
                f"{item.asset_name}: {currency} price cannot update "
                f"{item.currency} value without an exchange rate"
            )
            continue
        skipped.append(
            f"{item.asset_name}: {currency} quote saved, but "
            f"{reporting_currency} value was kept "
            "because an FX rate is unavailable"
        )
    return updated, skipped


def refresh_market_data(db: Session, force: bool = True) -> dict:
    preference = _preference(db)
    preference.last_attempt_at = _utcnow()
    symbols = _symbols(db)
    twelve_items = _twelve_data_investments(db)
    reporting_currency = base_currency(db)
    inr_rate, inr_fx_online = _refresh_fx_rate(
        db, "INR", reporting_currency
    )
    usd_rate, usd_fx_online = _refresh_fx_rate(
        db, "USD", reporting_currency
    )
    fx_online = inr_fx_online or usd_fx_online
    indian_investments_updated = _convert_indian_investments(
        db, inr_rate, reporting_currency
    )
    if not symbols and not twelve_items and not indian_investments_updated:
        preference.last_status = "no_symbols"
        preference.last_error = "Add a ticker to an investment or watchlist item."
        db.commit()
        return market_data_status(db)
    if not symbols and not twelve_items:
        preference.last_success_at = preference.last_attempt_at
        preference.last_status = "online" if fx_online else "offline"
        preference.last_error = (
            None
            if fx_online
            else f"Using cached INR to {reporting_currency} exchange rate."
        )
        db.commit()
        result = market_data_status(db)
        result.update(
            {
                "base_currency": reporting_currency,
                "fx_rate_inr_base": inr_rate,
                "fx_rate_usd_base": usd_rate,
                "fx_online": fx_online,
                "indian_investments_updated": indian_investments_updated,
            }
        )
        return result

    fetched_at = _utcnow()
    refreshed_symbols: list[str] = []
    failed_symbols: list[str] = []
    provider_errors: list[str] = []
    skipped_updates: list[str] = []
    investments_updated = 0
    try:
        finnhub_key = _api_key("finnhub")
        if symbols and not finnhub_key:
            provider_errors.append("Finnhub API key is not configured")
        elif symbols:
            with httpx.Client(
                base_url=_provider_url(),
                headers={"X-Finnhub-Token": finnhub_key},
                timeout=settings.market_data_timeout_seconds,
            ) as client:
                for symbol in symbols:
                    latest = db.scalar(
                        select(MarketPriceCache)
                        .where(
                            MarketPriceCache.symbol == symbol,
                            MarketPriceCache.interval == "intraday",
                        )
                        .order_by(MarketPriceCache.fetched_at.desc())
                    )
                    if not force and latest:
                        if fetched_at - _as_aware(latest.fetched_at) < timedelta(
                            minutes=5
                        ):
                            continue
                    try:
                        response = client.get("/quote", params={"symbol": symbol})
                        response.raise_for_status()
                        payload = response.json()
                        price = _decimal(payload.get("c"))
                        if price <= 0:
                            failed_symbols.append(symbol)
                            continue
                        timestamp = int(payload.get("t") or fetched_at.timestamp())
                        quote_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                        currency = (
                            latest.currency
                            if latest and latest.currency
                            else _profile_currency(client, symbol)
                        )
                        _store_quote(
                            db, symbol, price, currency, quote_time, fetched_at
                        )
                        count, skipped = _update_investments(
                            db,
                            symbol,
                            price,
                            currency,
                            fetched_at,
                            {"USD": usd_rate, "INR": inr_rate},
                        )
                        investments_updated += count
                        skipped_updates.extend(skipped)
                        refreshed_symbols.append(symbol)
                    except (httpx.HTTPError, ValueError, TypeError):
                        failed_symbols.append(symbol)

        twelve_key = _api_key("twelve_data")
        if twelve_items and not twelve_key:
            provider_errors.append("Twelve Data API key is not configured")
        elif twelve_items:
            with httpx.Client(
                base_url=_twelve_data_url(),
                timeout=settings.market_data_timeout_seconds,
            ) as client:
                for item in twelve_items:
                    symbol = str(item.ticker).upper()
                    cache_symbol = str(item.provider_symbol or item.ticker).upper()
                    try:
                        response = client.get(
                            "/time_series",
                            params={
                                "symbol": symbol,
                                "exchange": (
                                    "XETR"
                                    if str(item.exchange).upper() == "XETRA"
                                    else item.exchange or "XETR"
                                ),
                                "interval": "1day",
                                "outputsize": 1,
                                "apikey": twelve_key,
                            },
                        )
                        payload = response.json()
                        values = payload.get("values") or []
                        price = _decimal(values[0].get("close") if values else None)
                        if payload.get("status") == "error" or price <= 0:
                            failed_symbols.append(cache_symbol)
                            message = str(payload.get("message") or "Provider error")
                            if "Grow or Venture plan" in message:
                                item.quote_status = "subscription_required"
                                if (
                                    "Twelve Data Grow or Venture plan is required"
                                    not in provider_errors
                                ):
                                    provider_errors.append(
                                        "Twelve Data Grow or Venture plan is required"
                                    )
                            else:
                                item.quote_status = "provider_error"
                            continue
                        meta = payload.get("meta") or {}
                        currency = str(meta.get("currency") or "EUR").upper()
                        quote_time = datetime.fromisoformat(
                            str(values[0].get("datetime"))
                        ).replace(tzinfo=timezone.utc)
                        _store_quote(
                            db,
                            cache_symbol,
                            price,
                            currency,
                            quote_time,
                            fetched_at,
                            TWELVE_DATA_PROVIDER,
                        )
                        count, skipped = _update_investments(
                            db,
                            cache_symbol,
                            price,
                            currency,
                            fetched_at,
                            {"USD": usd_rate, "INR": inr_rate},
                            TWELVE_DATA_PROVIDER,
                        )
                        investments_updated += count
                        skipped_updates.extend(skipped)
                        refreshed_symbols.append(cache_symbol)
                    except (
                        httpx.HTTPError,
                        ValueError,
                        TypeError,
                        AttributeError,
                    ):
                        failed_symbols.append(cache_symbol)
                        item.quote_status = "provider_error"
        db.execute(
            delete(MarketPriceCache).where(
                MarketPriceCache.interval == "intraday",
                MarketPriceCache.fetched_at < fetched_at - timedelta(days=7),
            ),
            execution_options={"synchronize_session": False},
        )
        if refreshed_symbols or indian_investments_updated:
            preference.last_success_at = fetched_at
            preference.last_status = (
                "online"
                if not failed_symbols and not provider_errors
                else "online_partial"
            )
            errors = [
                *provider_errors,
                *(
                    [f"Could not refresh: {', '.join(failed_symbols)}"]
                    if failed_symbols
                    else []
                ),
            ]
            preference.last_error = ". ".join(errors) or None
        else:
            preference.last_status = "offline"
            preference.last_error = "Market provider could not be reached."
        db.commit()
    except (httpx.HTTPError, RuntimeError, OSError) as error:
        preference.last_status = "offline"
        preference.last_error = str(error)
        db.commit()

    result = market_data_status(db)
    result.update(
        {
            "refreshed_symbols": refreshed_symbols,
            "failed_symbols": failed_symbols,
            "investments_updated": investments_updated,
            "indian_investments_updated": indian_investments_updated,
            "base_currency": reporting_currency,
            "fx_rate_inr_base": inr_rate,
            "fx_rate_usd_base": usd_rate,
            "fx_online": fx_online,
            "skipped_portfolio_updates": skipped_updates,
        }
    )
    return result


def refresh_market_data_if_due(db: Session) -> dict:
    status = market_data_status(db)
    if status["refresh_due"]:
        return refresh_market_data(db, force=False)
    return status
