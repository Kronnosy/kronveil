"""
Kronos Veil - Main Entry Point.
"Your chat. Your screen. Invisible to stream."
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kronos_veil import __app_name__, __version__
from kronos_veil.app import KronosVeilApp
from kronos_veil.tray import create_default_icon


def setup_logging(debug: bool = False) -> None:
    """Configures structured application logging."""
    level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] (%(name)s) %(message)s"
    logging.basicConfig(level=level, format=log_format, datefmt="%H:%M:%S")


def handle_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
    """Catches unhandled exceptions to prevent silent crashes."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.critical(
        "Uncaught exception encountered:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"{__app_name__} v{__version__} — Private Streamer Chat Overlay"
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--reset-position", action="store_true", help="Reset overlay position to default")
    parser.add_argument("--config", type=str, default=None, help="Path to custom settings JSON file")

    args = parser.parse_args()

    setup_logging(debug=args.debug)
    sys.excepthook = handle_uncaught_exception

    logging.info("Starting %s v%s...", __app_name__, __version__)

    # Initialize PySide6 Application
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(__app_name__)
    qapp.setApplicationVersion(__version__)
    qapp.setOrganizationName("KronosVeil")
    qapp.setQuitOnLastWindowClosed(False)  # Remains active in tray when windows close

    # App icon
    assets_icon = Path(__file__).resolve().parent / "assets" / "icon.png"
    if assets_icon.exists():
        qapp.setWindowIcon(QIcon(str(assets_icon)))
    else:
        qapp.setWindowIcon(create_default_icon())

    # Instantiate Application Controller
    controller = KronosVeilApp(qapp, config_path=args.config)

    if args.reset_position:
        controller._reset_overlay_position()

    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
