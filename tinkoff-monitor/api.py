import datetime
import logging

import tinvest
from pydantic import ValidationError


log = logging.getLogger(__name__)


class Api:
    def __init__(self, token):
        self.client = tinvest.AsyncClient(token)
        # self.client._base_url = 'https://invest-public-api.tinkoff.ru/openapi'

        self.portfolio_api = tinvest.PortfolioApi(self.client)
        self.market_api = tinvest.MarketApi(self.client)
        self.figi_by_ticker = dict()
        self.currency_price = {
            tinvest.Currency.rub: 1.0,
        }

        self.currency_balance = {}

        self.ticker_for_currency = {
            tinvest.Currency.usd: 'USD000UTSTOM',
            tinvest.Currency.eur: 'EUR_RUB__TOM',
        }

    async def get_figi(self, ticker) -> str:
        if ticker not in self.figi_by_ticker:
            async with self.market_api.market_search_by_ticker_get(
                    ticker
            ) as resp:
                data: tinvest.MarketInstrumentList = (
                    await resp.parse_json()
                ).payload
                if not data.instruments:
                    raise ValueError(f"Can't find figi for {ticker}")

                self.figi_by_ticker[ticker] = data.instruments[0].figi

        return self.figi_by_ticker[ticker]

    async def last_day_candle(self, ticker) -> tinvest.Candle:
        figi = await self.get_figi(ticker)

        async with self.market_api.market_candles_get(
                figi=figi,
                from_=datetime.datetime.now() - datetime.timedelta(days=10),
                to=datetime.datetime.now(),
                interval=tinvest.CandleResolution.day
        ) as resp:
            cdata: tinvest.Candles = (await resp.parse_json()).payload
            return cdata.candles[-2] if len(cdata.candles) > 1 else cdata.candles[0]

    async def current_orders(self, ticker) -> tinvest.Orderbook:
        figi = await self.get_figi(ticker)
        async with self.market_api.market_orderbook_get(figi, 1) as resp:
            try:
                obdata: tinvest.Orderbook = (await resp.parse_json()).payload
            except ValidationError as e:
                log.warning(f"Error getting orderbook {ticker} [figi:{figi}] {e}")
                return None
            return obdata

    async def update_portfolio_currencies(self):
        async with self.portfolio_api.portfolio_currencies_get() as resp:
            currencies: tinvest.Currencies = (
                await resp.parse_json()
            ).payload

            for cur in currencies.currencies:
                self.currency_balance[cur.currency] = cur.balance
                if cur.currency == tinvest.Currency.rub:
                    continue

                if (obdata := await self.current_orders(
                    self.ticker_for_currency[cur.currency]
                )):
                    self.currency_price[cur.currency] = obdata.last_price
