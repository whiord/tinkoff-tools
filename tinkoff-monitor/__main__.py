import asyncio
import logging
import os
import signal
from pathlib import Path
from threading import Thread
from typing import Optional

from rumps import rumps
from tinkoff.invest import AsyncClient, InstrumentStatus, Quotation

from api import Api
from args import parser
from portfolio import PortfolioCalculator

log = logging.getLogger(__name__)


APPID = "Tinkoff"
CURDIR = Path(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_KEY = "PORTFOLIO"


with open(CURDIR / ".token", "r") as token:
    TOKEN = token.readline()


def price(q: Quotation):
    return q.units + q.nano/10**9


def main():
    # Handle pressing Ctr+C properly, ignored by default
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    args = parser.parse_args()

    menu_items = {
        ticker: rumps.MenuItem(ticker)
        for ticker in (
            [PORTFOLIO_KEY] if not args.disable_portfolio else []
        ) + args.tickers
    }

    class StatusBarApp(rumps.App):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            for item in menu_items.values():
                self.menu.add(item)

    app = StatusBarApp(
        APPID,
        icon="/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/AirDrop.icns",
    )

    async def update_tick(
            api: Api, portfolio_calc: Optional[PortfolioCalculator],
    ):
        # entries = []
        if portfolio_calc:
            # await portfolio_calc.update_tick()
            portfolio = await api.client.operations.get_portfolio(
                account_id=api.main_acc_id
            )
            sum_ = sum(map(price, [
                portfolio.total_amount_shares,
                portfolio.total_amount_bonds,
                portfolio.total_amount_futures,
                portfolio.total_amount_etf,
                portfolio.total_amount_currencies,
            ]))
            str_ = str(round(round(sum_), -3))

            L = len(str_)

            parts = [str_[max(0, L - 3 * i): L - 3 * i + 3] for i in
                     range((L - 1) // 3 + 1, 0, -1)]

            menu_items["PORTFOLIO"].title = (
                f"PORTFOLIO: {'.'.join(parts)} RUB"
            )

        for ticker in args.tickers:
            orderbook = await api.current_orders(ticker)
            candle = await api.last_day_candle(ticker)

            j_ticker = ticker.ljust(5, ' ')
            j_price = str(price(orderbook.last_price)).ljust(7, ' ')
            delta = price(orderbook.last_price) - price(candle.close)
            j_delta = f'{delta:.3}'.rjust(10, ' ')

            j_perc = f'{delta / price(candle.close) * 100:.2}' #.rjust(10, ' ')

            ticker_label = f'{j_ticker}: {j_price}  {j_delta}  |  {j_perc}%'
            menu_items[ticker].title = ticker_label

    async def worker():
        async with AsyncClient(TOKEN) as client:
            accounts = await client.users.get_accounts()

            api = Api(client, accounts.accounts[0].id)
            portfolio_calc = None
            if not args.disable_portfolio:
                portfolio_calc = PortfolioCalculator(api, args)

            while True:
                try:
                    await update_tick(api, portfolio_calc)
                except:
                    log.error("Exception while updating ticker", exc_info=True)
                    await asyncio.sleep(120)

                await asyncio.sleep(30)


    def async_loop():
        asyncio.run(worker())

    async_thread = Thread(target=async_loop, daemon=True)
    async_thread.start()

    app.run()


if __name__ == '__main__':
    main()


