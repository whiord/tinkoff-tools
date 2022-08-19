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

