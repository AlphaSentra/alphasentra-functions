from dataclasses import dataclass


@dataclass
class AssetMetadata:
    ticker: str
    name: str
    sector: str
    industry: str
    dividend_yield: float = 0.0
    market_cap: float = 0.0
    eps: float = 0.0
    ev_ebitda: float = 0.0
    eps_growth: float = 0.0
    forward_pe: float = 0.0
    roe: float = 0.0
    current_ratio: float = 0.0

    @classmethod
    def default(cls, ticker: str) -> "AssetMetadata":
        return cls(
            ticker=ticker,
            name=ticker,
            sector="Others",
            industry="Others",
        )
