import pandas as pd
from typing import Optional
from backend.tally_connector import TallyConnector

class LedgerLoader:
    """Class to load Tally ledger/voucher data from live Tally or fallback CSV/XLSX."""
    @staticmethod
    def load_csv(path: str, **kwargs) -> Optional[pd.DataFrame]:
        """Load a ledger/voucher CSV file and return as DataFrame (fallback only)."""
        try:
            df = pd.read_csv(path, **kwargs)
            return df
        except Exception as e:
            print(f"CSV load error: {e}")
            return None

    @staticmethod
    def load_xlsx(path: str, **kwargs) -> Optional[pd.DataFrame]:
        """Load a ledger/voucher XLSX file and return as DataFrame (fallback only)."""
        try:
            df = pd.read_excel(path, **kwargs)
            return df
        except Exception as e:
            print(f"XLSX load error: {e}")
            return None

    @staticmethod
    def load_tally_ledgers(company_name: str, tally_url: str = "http://localhost:9000") -> Optional[pd.DataFrame]:
        """Load ledgers directly from TallyPrime via XML-HTTP API."""
        try:
            tc = TallyConnector(tally_url)
            return tc.fetch_ledgers(company_name)
        except Exception as e:
            print(f"Live Tally fetch_ledgers error: {e}")
            return None

    @staticmethod
    def load_tally_vouchers(company_name: str, voucher_type: Optional[str] = None, tally_url: str = "http://localhost:9000") -> Optional[pd.DataFrame]:
        """Load vouchers from TallyPrime via XML-HTTP API."""
        try:
            tc = TallyConnector(tally_url)
            return tc.fetch_vouchers(company_name, voucher_type=voucher_type)
        except Exception as e:
            print(f"Live Tally fetch_vouchers error: {e}")
            return None
