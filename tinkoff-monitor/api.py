import datetime
import logging
from decimal import Decimal

import tinvest


log = logging.getLogger(__name__)


class Api:
    def __init__(self, token):
        self.client = tinvest.AsyncClient(token)
        # self.client._base_url = 'https://invest-public-api.tinkoff.ru/openapi'

        self.figi_by_ticker = dict()
        self.currency_price = {
            tinvest.Currency.rub: Decimal(1.0),
        }

        self.currency_balance = {}

        self.ticker_for_currency = {
            tinvest.Currency.usd: 'USD000UTSTOM',
            tinvest.Currency.eur: 'EUR_RUB__TOM',
            tinvest.Currency.hkd: 'HKD_RUB__TOM',
            tinvest.Currency.cny: 'CNY_RUB__TOM',
        }

    async def get_figi(self, ticker) -> str:
        if ticker not in self.figi_by_ticker:
            resp = await self.client.get_market_search_by_ticker(ticker)
            data: tinvest.MarketInstrumentList = resp.payload

            if not data.instruments:
                raise ValueError(f"Can't find figi for {ticker}")
            if data.total > 1:
                log.warning(
                    "More than one instrument found for ticker %s", ticker,
                )
            self.figi_by_ticker[ticker] = data.instruments[0].figi

        return self.figi_by_ticker[ticker]

    async def last_day_candle(self, ticker) -> tinvest.Candle:
        figi = await self.get_figi(ticker)

        resp = await self.client.get_market_candles(
            figi=figi,
            from_=datetime.datetime.now() - datetime.timedelta(days=10),
            to=datetime.datetime.now(),
            interval=tinvest.CandleResolution.day,
        )
        data: tinvest.Candles = resp.payload
        return data.candles[-2] if len(data.candles) > 1 else data.candles[0]

    async def current_orders(self, ticker) -> tinvest.Orderbook:
        figi = await self.get_figi(ticker)
        resp = await self.client.get_market_orderbook(figi, 1)
        return resp.payload

    async def update_portfolio_currencies(self):
        resp = await self.client.get_portfolio_currencies()
        currencies = resp.payload

        for cur in currencies.currencies:
            self.currency_balance[cur.currency] = cur.balance
            if cur.currency == tinvest.Currency.rub:
                continue

            if (orders := await self.current_orders(
                self.ticker_for_currency[cur.currency]
            )):
                self.currency_price[cur.currency] = orders.last_price
