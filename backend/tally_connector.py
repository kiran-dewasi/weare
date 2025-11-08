import requests
import xml.etree.ElementTree as ET
import pandas as pd
from typing import Optional, Dict, Any

class TallyConnector:
    """
    Connector for TallyPrime XML-HTTP interface.
    Supports reading ledgers/vouchers and pushing updates directly to Tally.
    """

    def __init__(self, url: str = "http://localhost:9000"):
        self.url = url

    def send_request(self, xml: str) -> str:
        """Send an XML request to Tally and return raw response text."""
        headers = {"Content-Type": "application/xml"}
        try:
            resp = requests.post(self.url, data=xml.encode("utf-8"), headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            raise RuntimeError(f"TallyConnector HTTP error: {e}")

    def fetch_ledgers(self, company_name: str) -> pd.DataFrame:
        """Fetch all ledgers from the specified Tally company as a pandas DataFrame."""
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
            <BODY>
                <EXPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>List of Ledgers</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
                        </STATICVARIABLES>
                    </REQUESTDESC>
                </EXPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        return self._parse_ledger_xml(xml_response)

    def fetch_ledgers_full(self, company_name: str) -> pd.DataFrame:
        """Fetch all ledgers with full detail (including GSTIN, PAN, etc.)."""
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
            <BODY>
                <EXPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>Ledger</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
                        </STATICVARIABLES>
                    </REQUESTDESC>
                </EXPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        # Parse out GSTIN, addresses, and other fields (if present in <LEDGER>)
        return self._parse_ledger_xml(xml_response)

    def fetch_vouchers(self, company_name: str, voucher_type: Optional[str] = None) -> pd.DataFrame:
        """Fetch all vouchers or by type."""
        voucher_type_xml = f"<VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>" if voucher_type else ""
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
            <BODY>
                <EXPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>Voucher Register</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
                            {voucher_type_xml}
                        </STATICVARIABLES>
                    </REQUESTDESC>
                </EXPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        return self._parse_voucher_xml(xml_response)

    def push_voucher(self, company_name: str, voucher_xml: str) -> Dict[str, Any]:
        """Push a single voucher update to Tally (voucher_xml is <VOUCHER>...</VOUCHER> block as string)."""
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
            <BODY>
                <IMPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>Vouchers</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
                        </STATICVARIABLES>
                    </REQUESTDESC>
                    <REQUESTDATA>
                        <TALLYMESSAGE>
                            {voucher_xml}
                        </TALLYMESSAGE>
                    </REQUESTDATA>
                </IMPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        return {"status": self._parse_response_status(xml_response), "raw": xml_response}

    @staticmethod
    def _parse_ledger_xml(xml_text: str) -> pd.DataFrame:
        """Parse Tally ledger XML into a pandas DataFrame (minimal parser for demo; extend as needed)."""
        root = ET.fromstring(xml_text)
        rows = []
        for ledger in root.iter("LEDGER"):
            data = {child.tag: child.text for child in ledger}
            rows.append(data)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    @staticmethod
    def _parse_voucher_xml(xml_text: str) -> pd.DataFrame:
        """Parse Tally voucher XML into a pandas DataFrame (minimal version)."""
        root = ET.fromstring(xml_text)
        rows = []
        for voucher in root.iter("VOUCHER"):
            data = {child.tag: child.text for child in voucher}
            rows.append(data)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    @staticmethod
    def _parse_response_status(xml_text: str) -> str:
        """Parse a simple <RESPONSE> or status tag from Tally response XML."""
        try:
            root = ET.fromstring(xml_text)
            resp = root.find("RESPONSE")
            return resp.text.strip() if resp is not None else "OK"
        except Exception:
            return "Unknown"

def get_customer_details(ledgers_df: pd.DataFrame, party_name: str) -> dict:
    """
    Given a ledgers DataFrame and a party name, fetch GSTIN, PAN, address, etc.
    Returns a dict with the found details, otherwise empty dict. Adjust field names per your Tally export.
    """
    if ledgers_df.empty:
        print(f"[LOG] Ledgers DataFrame is empty, cannot lookup '{party_name}'")
        return {}
    
    # Try common column name variations for ledger name
    name_col = None
    for col_name in ['NAME', 'LEDGERNAME', 'LEDGER_NAME', 'PARTYNAME']:
        if col_name in ledgers_df.columns:
            name_col = col_name
            break
    
    if name_col is None:
        print(f"[WARN] No recognized name column found in ledgers. Available columns: {list(ledgers_df.columns)}")
        return {}
    
    try:
        match = ledgers_df[ledgers_df[name_col].astype(str).str.lower() == party_name.lower()]
        if match.empty:
            print(f"[LOG] Customer '{party_name}' not found in live ledgers (fallback?)")
            return {}
        row = match.iloc[0].to_dict()
        details = {
            'GSTIN': row.get('GSTIN', '') or row.get('GSTIN/UIN', ''),
            'PAN': row.get('INCOMETAXNUMBER', '') or row.get('PAN', ''),
            'ADDRESS': row.get('ADDRESS', '') or row.get('MAILINGNAME', ''),
            # Add/adjust fields to suit your Tally ledger XML!
        }
        print(f"[LOG] Enriched customer details for '{party_name}': {details}")
        return details
    except Exception as ex:
        print(f"[ERROR] Failed to lookup customer '{party_name}': {ex}")
        return {}

# Example usage:
if __name__ == "__main__":
    tc = TallyConnector()
    company = "SHREE JI SALES"  # Replace this with your actual company name!
    print("Fetching ledgers...")
    df_ledgers = tc.fetch_ledgers(company)
    print(df_ledgers.head())
