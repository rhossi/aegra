#!/usr/bin/env python3
"""
Server startup script for testing.

This script:
1. Sets up the environment
2. Starts the FastAPI server
3. Can be used for testing our LangGraph integration
"""

import logging
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Add graphs directory to Python path so imports can be resolved
current_dir = Path(__file__).parent
graphs_dir = current_dir / "graphs"
if str(graphs_dir) not in sys.path:
    sys.path.insert(0, str(graphs_dir))


def setup_environment():
    """Set up environment variables for testing"""
    # Set database URL for development
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = (
            "postgresql+asyncpg://user:password@localhost:5432/aegra"
        )

    # Set auth type (can be overridden)
    if not os.getenv("AUTH_TYPE"):
        os.environ["AUTH_TYPE"] = "noop"

    print(f"🔐 Auth Type: {os.getenv('AUTH_TYPE')}")
    print(f"🗄️  Database: {os.getenv('DATABASE_URL')}")


def configure_logging(level: str = "DEBUG"):
    """Configure root and app loggers to emit to stdout with formatting."""
    log_level = getattr(logging, level.upper(), logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers on reload
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        root.addHandler(sh)

    # Ensure our package/module loggers are at least at the configured level
    logging.getLogger("agent_server").setLevel(log_level)
    logging.getLogger("src.agent_server").setLevel(log_level)
    logging.getLogger("aegra").setLevel(log_level)
    logging.getLogger("uvicorn.error").setLevel(log_level)
    logging.getLogger("uvicorn.access").setLevel(log_level)


def main():
    """Start the server"""
    setup_environment()
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))

    port = int(os.getenv("PORT", "8000"))

    print("🚀 Starting Aegra...")
    print(f"📍 Server will be available at: http://localhost:{port}")
    print(f"📊 API docs will be available at: http://localhost:{port}/docs")
    print("🧪 Test with: python test_sdk_integration.py")

    uvicorn.run(
        "src.agent_server.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "debug"),
    )


if __name__ == "__main__":
    load_dotenv()
    main()
