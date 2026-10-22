"""Entry point for running the worker as a separate process: `python -m app.worker`."""

import asyncio

from app.orchestration.worker import main

if __name__ == "__main__":
    asyncio.run(main())
