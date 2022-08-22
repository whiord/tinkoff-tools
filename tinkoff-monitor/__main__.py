import asyncio
import logging
import os
from pathlib import Path
from threading import Thread
from typing import Optional

from rumps import rumps

from api import Api
from args import parser
from portfolio import PortfolioCalculator

log = logging.getLogger(__name__)


APPID = "Tinkoff"
CURDIR = Path(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_KEY = "PORTFOLIO"

with open(CURDIR / ".token", "r") as token:
    TOKEN = token.readline()


def main():
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
        entries = []
        if portfolio_calc:
            await portfolio_calc.update_tick()
            menu_items["PORTFOLIO"].title = portfolio_calc.last_str

        for ticker in args.tickers:
            obdata = await api.current_orders(ticker)
            cdata = await api.last_day_candle(ticker)

            j_ticker = ticker.ljust(5, ' ')
            j_price = str(obdata.last_price).ljust(7, ' ')
            delta = (obdata.last_price - cdata.c)
            j_delta = f'{delta:.3}'.rjust(10, ' ')

            j_perc = f'{delta / cdata.c * 100:.2}' #.rjust(10, ' ')

            ticker_label = f'{j_ticker}: {j_price}  {j_delta}  |  {j_perc}%'
            menu_items[ticker].title = ticker_label

    async def worker():
        api = Api(TOKEN)
        portfolio_calc = None
        if not args.disable_portfolio:
            portfolio_calc = PortfolioCalculator(api, args)

        while True:
            try:
                await update_tick(api, portfolio_calc)
            except:
                log.error("Exception while updating ticker", exc_info=True)
                await asyncio.sleep(120)
                continue

    def async_loop():
        asyncio.run(worker())

    async_thread = Thread(target=async_loop, daemon=True)
    async_thread.start()

    app.run()


if __name__ == '__main__':
    main()


