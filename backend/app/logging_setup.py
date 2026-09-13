"""Make application logs reach the host's log stream.

uvicorn configures only its own loggers and leaves the root logger alone, so
without this every ``logger.info`` in the app is dropped and ``logger.warning``
survives only via Python's last-resort handler. That silence is expensive: a
storage path resolving to the wrong place, or the fixture-placement pass
falling back, both look identical to nothing happening.
"""

import logging
import os

DEFAULT_LEVEL = "INFO"
FORMAT = "%(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Attach a stdout handler to the root logger.

    ``basicConfig`` is a no-op when the root logger already has handlers, so
    calling this twice, or after a host has set up its own logging, is safe.
    """
    logging.basicConfig(
        level=(level or os.getenv("LOG_LEVEL", DEFAULT_LEVEL)).upper(),
        format=FORMAT,
    )
