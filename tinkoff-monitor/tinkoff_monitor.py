#!/usr/bin/python3
import asyncio
import datetime
import logging
import signal
import os
from collections import defaultdict
from pathlib import Path
from threading import Thread
from typing import Dict

import gi
import tinvest as tinvest
from pydantic import ValidationError

gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk
from gi.repository import Notify
from gi.repository import GLib
from gi.repository import AppIndicator3
from gi.repository import Gdk


log = logging.getLogger(__name__)


APPID = "Tinkoff"
CURDIR = Path(os.path.dirname(os.path.abspath(__file__)))

with open(CURDIR / ".token", "r") as token:
    TOKEN = token.readline().encode()


# Cross-platform tray icon implementation
class TrayIcon:
    def __init__(self, appid):
        self.ind = AppIndicator3.Indicator.new(
            appid, 'new-messages',
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)


class AsyncMenuItem(Gtk.MenuItem):
    async def set_label(self, label):
        GLib.idle_add(
            super().set_label,
            label
        )


class Api:
    def __init__(self):
        self.client = tinvest.AsyncClient(TOKEN)
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


class PortfolioCalculator:
    def __init__(self, api: Api, args):
        self.api = api
        self.portfolio_api = api.portfolio_api
        self.args = args

        self.last_str = None

    async def update_tick(self):
        api = self.api

        daily_change_by_currency = defaultdict(int)

        await api.update_portfolio_currencies()

        summary = (
                self.args.fixup_rub +
                self.args.fixup_usd * api.currency_price[tinvest.Currency.usd]
        )
        summary += api.currency_balance[tinvest.Currency.rub]

        async with api.portfolio_api.portfolio_get() as resp:
            portfolio: tinvest.Portfolio = (
                await resp.parse_json()
            ).payload

            for pos in portfolio.positions:
                obdata = await api.current_orders(pos.ticker)

                summary += (
                        pos.balance * obdata.last_price
                        * api.currency_price[pos.expected_yield.currency]
                )

                if pos.instrument_type == tinvest.InstrumentType.bond:
                    summary += (
                            pos.expected_yield.value
                            * api.currency_price[pos.expected_yield.currency]
                    )

                last_candle = await api.last_day_candle(pos.ticker)
                daily_change_by_currency[pos.expected_yield.currency] += (
                        (obdata.last_price - last_candle.c) * pos.balance
                )

        summary_str = str(round(round(summary), -3))
        L = len(summary_str)

        parts = [summary_str[max(0, L - 3 * i): L - 3 * i + 3] for i in
                 range((L - 1) // 3 + 1, 0, -1)]

        daily_change = sum(
            map(
                lambda k: api.currency_price[k[0]] * k[1],
                list(daily_change_by_currency.items())
            )
        )

        percent = daily_change/(summary - daily_change)

        portfolio_str = (
            f'{".".join(parts)} | '
            f'{"+" if daily_change > 0 else ""}{round(daily_change)} RUB'
            f' | {round(100 * percent, 2)}%'
            # f'{" | " .join(f"{round(v)} {k}" for k, v in daily_change_by_currency.items())}'
        )

        self.last_str = portfolio_str


def main():
    # Handle pressing Ctr+C properly, ignored by default
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tickers", nargs='*',
    )
    parser.add_argument("--fixup-rub", type=int, default=0)
    parser.add_argument("--fixup-usd", type=int, default=0)
    parser.add_argument(
        "--disable-portfolio", default=False, action="store_true"
    )
    parser.add_argument("--interval", type=int, default=60)

    args = parser.parse_args()

    print("Tickers:", args.tickers)

    menu_items_by_key: Dict[str, AsyncMenuItem] = {}

    if not args.disable_portfolio:
        menu_items_by_key["PORTFOLIO"] = AsyncMenuItem()

    menu_items_by_key.update(
        {
            ticker: AsyncMenuItem()
            for ticker in args.tickers
        }
    )

    def update_label(label):
        icon.ind.set_label(label, '')

    def update_ind_icon(icon_name):
        icon.ind.set_icon(icon_name)

    def async_loop():
        loop = asyncio.new_event_loop()
        loop.run_until_complete(worker())

    async def update_tick(api: Api, portfolio_calc: PortfolioCalculator):
        entries = []
        if portfolio_calc:
            await portfolio_calc.update_tick()

            portfolio_str = portfolio_calc.last_str

            await menu_items_by_key["PORTFOLIO"].set_label(portfolio_str)
            GLib.idle_add(
                update_label, portfolio_str
            )

            entries.append(portfolio_str)

        for ticker in args.tickers:
            obdata = await api.current_orders(ticker)
            cdata = await api.last_day_candle(ticker)

            j_ticker = ticker.ljust(5, ' ')
            j_price = str(obdata.last_price).ljust(7, ' ')
            delta = (obdata.last_price - cdata.c)
            j_delta = f'{delta:.3}'.rjust(10, ' ')

            j_perc = f'{delta / cdata.c * 100:.2}' #.rjust(10, ' ')

            ticker_label = f'{j_ticker}: {j_price}  {j_delta}  |  {j_perc}%'
            await menu_items_by_key[ticker].set_label(ticker_label)
            entries.append(ticker_label)

        Notify.Notification.new("TINKOFF", "\n".join(entries)).show()

    async def worker():
        api = Api()

        portfolio_calc = None
        if not args.disable_portfolio:
            portfolio_calc = PortfolioCalculator(api, args)

        icon = 'new-messages'
        while True:
            try:
                await update_tick(api, portfolio_calc)
            except:
                GLib.idle_add(update_ind_icon, 'state-error')
                log.error("Exception while updating ticker", exc_info=True)
                await asyncio.sleep(120)
                continue

            if icon == 'new-messages':
                icon = 'new-messages-red'
            else:
                icon = 'new-messages'

            GLib.idle_add(update_ind_icon, icon)
            await asyncio.sleep(args.interval)

    async_thread = Thread(target=async_loop, daemon=True)
    async_thread.start()

    menu = Gtk.Menu()
    for ticker_item in menu_items_by_key.values():
        menu.append(ticker_item)
        ticker_item.show()

    quit_item = Gtk.MenuItem(label='Quit')
    quit_item.connect('activate', Gtk.main_quit)
    quit_item.show()
    menu.append(quit_item)

    icon = TrayIcon(APPID)
    icon.ind.set_menu(menu)

    ###
    css = b'* { font-family: monospace; font-size: 10px; }'
    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(css)
    context = Gtk.StyleContext()
    screen = Gdk.Screen.get_default()
    context.add_provider_for_screen(screen, css_provider,
                                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    ###

    Notify.init(APPID)

    # win.add(view)
    # win.show_all()
    Gtk.main()

if __name__ == '__main__':
    main()
