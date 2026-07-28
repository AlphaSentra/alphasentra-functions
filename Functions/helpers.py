"""
Helper functions
"""

import os
from typing import Tuple
from urllib.parse import quote_plus
from logging_utils import log_error, log_info

from Functions.db.client import DatabaseManager
from Functions.db.repositories import (
    get_ticker_by_etoro_symbol,
    get_ticker_and_name_by_etoro_symbol,
)

__all__ = [
    "DatabaseManager",
    "get_ticker_by_etoro_symbol",
    "get_ticker_and_name_by_etoro_symbol",
]

