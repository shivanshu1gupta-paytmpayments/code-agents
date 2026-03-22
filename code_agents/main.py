from .env_loader import load_all_env
load_all_env()

import os
import uvicorn

from .config import settings
from .logging_config import setup_logging


def main():
    setup_logging()

    log_level = os.getenv("LOG_LEVEL", "info").lower()
    uvicorn.run(
        "code_agents.app:app",
        host=settings.host,
        port=settings.port,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
