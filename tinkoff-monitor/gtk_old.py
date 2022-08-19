#!/usr/bin/python3
import asyncio
import logging
import signal
import os
from pathlib import Path
from threading import Thread
from typing import Dict

import gi

from api import Api
from args import parser
from portfolio import PortfolioCalculator

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


def main():
    # Handle pressing Ctr+C properly, ignored by default
    signal.signal(signal.SIGINT, signal.SIG_DFL)

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
        api = Api(TOKEN)

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
