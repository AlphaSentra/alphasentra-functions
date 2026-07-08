from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class EToroSocialTrade:
    investor_id: str
    investor_name: str
    leverage: float
    is_sell: bool
    position_id: str
    copy_close_time: Optional[datetime]


@dataclass
class EToroPortfolioPosition:
    position_id: str
    instrument_id: str
    symbol: Optional[str]
    display_name: Optional[str]
    symbol_full: Optional[str]
    open_timestamp: Optional[datetime] = None
    open_rate: Optional[float] = None
    is_buy: bool = False
    leverage: float = 1.0
    take_profit_rate: Optional[float] = None
    stop_loss_rate: Optional[float] = None
    investment_pct: Optional[float] = None
    net_profit: Optional[float] = None
    realized_credit_pct: Optional[float] = None
    unrealized_credit_pct: Optional[float] = None
    social_trades: List[EToroSocialTrade] = field(default_factory=list)


@dataclass
class EToroAggregatedPosition:
    symbol: Optional[str]
    weight: float
    trade_direction: str
    average_entry_price: float
    position_count: int
    instrument_id: Optional[str] = None
    symbol_full: Optional[str] = None


@dataclass
class EToroInvestorPortfolio:
    username: str
    positions: List[EToroPortfolioPosition]
    aggregated_positions: List[EToroAggregatedPosition] = field(default_factory=list)


@dataclass
class EToroGainPoint:
    date: datetime
    gain: float


@dataclass
class EToroGainHistory:
    username: str
    granularity: str
    total_gain: Optional[float]
    gains: List[EToroGainPoint]


@dataclass
class EToroTradeRecord:
    raw: Dict[str, Any]


@dataclass
class EToroTradeHistory:
    def __init__(self, cid: str, records: List[EToroTradeRecord], page: int, items_per_page: int, total_items: int):
        self.cid = cid
        self.records = records
        self.page = page
        self.items_per_page = items_per_page
        self.total_items = total_items


@dataclass
class EToroUser:
    username: str
    gcid: Optional[int]
    real_cid: Optional[int]
    demo_cid: Optional[int]


class EToroUserLookupResult:
    def __init__(self, by_cid: Dict[str, EToroUser], requested: List[str]):
        self.by_cid = by_cid
        self.requested = requested
