import datetime
import logging

from tinkoff.invest import (
    Candle, CandleInterval, GetOrderBookResponse, InstrumentIdType,
    InstrumentStatus, InstrumentType, OrderBook,
)
from tinkoff.invest.async_services import AsyncServices

log = logging.getLogger(__name__)


class Api:
    def __init__(self, client: AsyncServices, main_acc_id):
        self.client = client

        self.accounts = []
        self.main_acc_id = main_acc_id

        self.share_by_ticker = {}

        self.currency_price = {
            "rub": 1.0,
        }

        self.currency_balance = {}

        self.ticker_for_currency = {
            "usd": 'USD000UTSTOM',
            "eur": 'EUR_RUB__TOM',
            "hkd": 'HKD_RUB__TOM',
            "cny": 'CNY_RUB__TOM',
        }

    async def get_figi(self, ticker) -> str:
        if ticker not in self.share_by_ticker:
            shares = await self.client.instruments.shares(
                instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE,
            )
            self.share_by_ticker = {
                sh.ticker: sh
                for sh in shares.instruments
            }

        # if ticker not in self.figi_by_ticker:
        #     resp = await self.client.instruments.get_instrument_by(
        #         id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_TICKER,
        #         id=ticker,
        #         class_code="",
        #     )
        #
        #     figi = resp.instrument.figi
        #     self.figi_by_ticker[ticker] = figi

            # resp = await self.client.get_market_search_by_ticker(ticker)
            # data: tinvest.MarketInstrumentList = resp.payload
            #
            # if not data.instruments:
            #     raise ValueError(f"Can't find figi for {ticker}")
            # if data.total > 1:
            #     log.warning(
            #         "More than one instrument found for ticker %s", ticker,
            #     )
            # self.figi_by_ticker[ticker] = data.instruments[0].figi

        return self.share_by_ticker[ticker].figi

    async def last_day_candle(self, ticker) -> Candle:
        figi = await self.get_figi(ticker)

        resp = await self.client.market_data.get_candles(
            figi=figi,
            from_=datetime.datetime.now() - datetime.timedelta(days=10),
            to=datetime.datetime.now(),
            interval=CandleInterval.CANDLE_INTERVAL_DAY,
        )
        candles = resp.candles
        return candles[-2] if len(candles) > 1 else candles[0]

    async def current_orders(self, ticker) -> GetOrderBookResponse:
        figi = await self.get_figi(ticker)
        resp = await self.client.market_data.get_order_book(
            figi=figi,
            depth=1,
        )
        return resp

    async def update_portfolio_currencies(self):
        portfolio = await self.client.operations.get_portfolio(
            account_id=self.main_acc_id,
        )
        # resp = await self.client.get_portfolio_currencies()
        # currencies = resp.payload
        # positions = (await self.client.get_portfolio()).payload

        # async with self.tclient as client:
        #     currencies = await client.instruments.currencies()
        currencies = [
            position
            for position in portfolio.positions
            if position.instrument_type == InstrumentType.INSTRUMENT_TYPE_CURRENCY
        ]

        for cur in currencies:
            self.currency_balance[cur.figi] = cur.current_price
            if cur.currency == tinvest.Currency.rub:
                continue

            if (orders := await self.current_orders(
                self.ticker_for_currency[cur.currency]
            )):
                self.currency_price[cur.currency] = orders.last_price
