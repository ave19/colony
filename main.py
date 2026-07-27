#!/usr/bin/env python3
"""Colony server entrypoint."""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Colony — first playable slice")
    parser.add_argument("--host", default=os.environ.get("COLONY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("COLONY_PORT", "8765")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "colony.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
