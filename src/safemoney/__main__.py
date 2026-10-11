"""python -m safemoney: serve the API and the built UI on 127.0.0.1:4102."""

from __future__ import annotations

import logging

import uvicorn

from .api import create_app
from .config import load_settings


def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # One worker on purpose: approvals and the trace stream live in memory.
    uvicorn.run(create_app(), host=settings.host, port=settings.port, workers=1, log_level="info")


if __name__ == "__main__":
    main()
