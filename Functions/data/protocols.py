from abc import ABC, abstractmethod
import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    def download_price_data(self, tickers, start_date, end_date) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_sector_industry_data(self, tickers) -> pd.DataFrame:
        pass
