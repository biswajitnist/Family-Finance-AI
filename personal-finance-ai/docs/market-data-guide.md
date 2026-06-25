# Market Data and Offline Mode

Ledger Local works primarily offline. Transactions, statements, OCR, budgets,
reports, financial chat, net worth, investments, loans, properties, and local
AI remain available without an internet connection.

## What requires internet

Current stock, ETF, and cryptocurrency prices require an approved market-data
provider. Ledger Local currently supports Finnhub only.

Only ticker symbols are sent to Finnhub. Transactions, account balances,
documents, names, budgets, and other personal finance data are never sent.

## Enabling Finnhub

The easiest option is to open the Market Data Status card and enter the key in
the **Finnhub API key** field. Select **Save API Key**. The key is stored in a
local file readable only by the current operating-system user and is never
returned to the browser after saving.

Alternatively, add this setting to the local `.env` file:

`FINANCE_FINNHUB_API_KEY=your_key`

Restart the backend after changing the setting. The Market Data Status card
will then enable **Refresh Market Data**.

## Refresh behavior

The Market Data Status card is available on Dashboard, Investments, and
Watchlist. Refreshing sends only saved ticker symbols to Finnhub, stores prices
in local SQLite, and updates eligible portfolio values.

Intraday snapshots are retained for seven days. One daily snapshot is kept
without an expiry limit.

## Currency safety

Ledger Local does not guess exchange rates. A holding value is recalculated
only when quantity is available and the provider currency matches the holding
currency. The downloaded quote is still cached when those fields are missing.

## Offline behavior

If Finnhub or the internet is unavailable, the portfolio, watchlist, cached
prices, reports, budgeting, and local AI remain available. Ledger Local shows
the latest cache time and the message **Offline Using Cached Data**.

## Automatic refresh

Available intervals are Manual only, every 15 minutes, every 30 minutes, every
1 hour, and Daily. The default is every 1 hour. Automatic refresh runs locally
while the backend application is running.
