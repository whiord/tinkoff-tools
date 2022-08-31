from collections import defaultdict

from api import Api


class PortfolioCalculator:
    def __init__(self, api: Api, args):
        self.api = api
        self.client = api.client

        self.main_acc_id: str = ""

        self.args = args
        self.last_str = None

    # async def init_main_acc(self):


    async def update_tick(self):
        # if not self.main_acc_id:
        #     await self.init_main_acc()

        api = self.api

        daily_change_by_currency = defaultdict(int)

        await api.update_portfolio_currencies()

        summary = (
                self.args.fixup_rub +
                self.args.fixup_usd * api.currency_price[tinvest.Currency.usd]
        )
        summary += api.currency_balance[tinvest.Currency.rub]

        resp = await self.client.get_portfolio()
        portfolio = resp.payload

        for pos in portfolio.positions:
            orders = await api.current_orders(pos.ticker)

            summary += (
                pos.balance * orders.last_price
                * api.currency_price[pos.expected_yield.currency]
            )

            if pos.instrument_type == tinvest.InstrumentType.bond:
                summary += (
                    pos.expected_yield.value
                    * api.currency_price[pos.expected_yield.currency]
                )

            last_candle = await api.last_day_candle(pos.ticker)
            daily_change_by_currency[pos.expected_yield.currency] += (
                (orders.last_price - last_candle.c) * pos.balance
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
