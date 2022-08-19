import asyncio
import logging
import os
from pathlib import Path
from threading import Thread

from api import Api
from args import parser

log = logging.getLogger(__name__)


APPID = "Tinkoff"
CURDIR = Path(os.path.dirname(os.path.abspath(__file__)))

with open(CURDIR / ".token", "r") as token:
    TOKEN = token.readline().encode()


def main():
    args = parser.parse_args()

    api = Api(TOKEN)

    async def worker():
        pass

    def async_loop():
        asyncio.run(worker())

    async_thread = Thread(target=async_loop, daemon=True)
    async_thread.start()


if __name__ == '__main__':
    main()


