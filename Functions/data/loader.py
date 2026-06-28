"""
Data loading utilities for portfolio and transaction data.
"""

import pandas as pd


def load_transactions_from_csv(file_path="transactions.csv"):
    """
    Loads transaction data from a CSV file, processes dates and ticker symbols.

    Args:
        file_path (str): Path to the CSV file containing transaction data.

    Returns:
        pd.DataFrame: A DataFrame with processed transaction data.
    """
    print(f"Loading transactions from {file_path}...")
    try:
        transactions_df = pd.read_csv(file_path)

        # Convert 'Date' column to datetime objects (DD/MM/YYYY format)
        transactions_df["Date"] = pd.to_datetime(transactions_df["Date"], format="%d/%m/%Y")

        # Convert 'Ticker' from .ASX to .AX
        transactions_df["Ticker"] = transactions_df["Ticker"].replace(r"\.ASX$", ".AX", regex=True)

        # Ensure numeric columns are indeed numeric
        transactions_df["Quantity"] = pd.to_numeric(transactions_df["Quantity"])
        transactions_df["Price"] = pd.to_numeric(transactions_df["Price"])
        transactions_df["Fees"] = pd.to_numeric(transactions_df["Fees"]).fillna(0)

        print(f"Successfully loaded {len(transactions_df)} transactions.")
        return transactions_df
    except FileNotFoundError:
        print(f"Error: Transaction file not found at {file_path}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error loading or processing transactions CSV: {e}")
        return pd.DataFrame()
