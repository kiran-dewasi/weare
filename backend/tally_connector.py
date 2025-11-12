import requests
import xml.etree.ElementTree as ET
import pandas as pd
from typing import Optional, Dict, Any
from xml.sax.saxutils import escape
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tally_import")

def parse_xml_safely(xml_text):
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"XML ParseError: {e}; raw: {xml_text[:2000]}")
        return None

def _strip_namespace(tag):
    return tag.split('}', 1)[-1] if '}' in tag else tag

def flatten_element(element):
    data = {}
    for child in element:
        tag = _strip_namespace(child.tag).upper().replace(' ', '_')
        if list(child):  # has children, flatten recursively
            data.update({f"{tag}_{k}": v for k, v in flatten_element(child).items()})
        else:
            data[tag] = (child.text or '').strip()
    return data

def normalize_columns(df):
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df

class TallyConnector:
    """
    Connector for TallyPrime XML-HTTP interface.
    Supports reading ledgers/vouchers and pushing updates directly to Tally.
    """
    def __init__(self, url, timeout=15, company_name=None):
        self.url = url
        self.timeout = timeout
        self.company_name = company_name

    def send_request(self, xml: str) -> str:
        headers = {"Content-Type": "application/xml"}
        try:
            resp = requests.post(self.url, data=xml.encode("utf-8"), headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            raise RuntimeError(f"TallyConnector HTTP error: {e}")

    def fetch_ledgers(self, company_name: Optional[str] = None) -> pd.DataFrame:
        cname = company_name or self.company_name
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
            <BODY>
                <EXPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>List of Ledgers</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{escape(cname)}</SVCURRENTCOMPANY>
                        </STATICVARIABLES>
                    </REQUESTDESC>
                </EXPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        return self._parse_ledger_xml(xml_response)

    def fetch_ledgers_full(self, company_name: Optional[str] = None) -> pd.DataFrame:
        cname = company_name or self.company_name
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
            <BODY>
                <EXPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>Ledger</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{escape(cname)}</SVCURRENTCOMPANY>
                        </STATICVARIABLES>
                    </REQUESTDESC>
                </EXPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        return self._parse_ledger_xml(xml_response)

    def fetch_vouchers(self, company_name: Optional[str] = None, voucher_type: Optional[str] = None) -> pd.DataFrame:
        cname = company_name or self.company_name
        voucher_type_xml = f"<VOUCHERTYPENAME>{escape(voucher_type)}</VOUCHERTYPENAME>" if voucher_type else ""
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
            <BODY>
                <EXPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>Voucher Register</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{escape(cname)}</SVCURRENTCOMPANY>
                            {voucher_type_xml}
                        </STATICVARIABLES>
                    </REQUESTDESC>
                </EXPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        return self._parse_voucher_xml(xml_response)

    def push_voucher(self, company_name: Optional[str], voucher_xml: str) -> Dict[str, Any]:
        cname = company_name or self.company_name
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
            <BODY>
                <IMPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>Vouchers</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{escape(cname)}</SVCURRENTCOMPANY>
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
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logging.error(f"XML ParseError: {e}; raw: {xml_text[:2000]}")
            return pd.DataFrame()
        rows = []
        for ledger in root.iter("LEDGER"):
            data = flatten_element(ledger)
            rows.append(data)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    @staticmethod
    def _parse_voucher_xml(xml_text: str) -> pd.DataFrame:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logging.error(f"XML ParseError: {e}; raw: {xml_text[:2000]}")
            return pd.DataFrame()
        rows = []
        for voucher in root.iter("VOUCHER"):
            data = flatten_element(voucher)
            rows.append(data)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    @staticmethod
    def _parse_response_status(xml_text: str) -> str:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logging.error(f"XML ParseError: {e}; raw: {xml_text[:2000]}")
            return "Unknown"
        resp = root.find("RESPONSE")
        return resp.text.strip() if resp is not None else "OK"

def get_customer_details(ledgers_df: pd.DataFrame, party_name: str) -> dict:
    if ledgers_df.empty:
        logger.warning(f"Ledgers DataFrame is empty, cannot lookup '{party_name}'")
        return {}
    ledgers_df = normalize_columns(ledgers_df)
    name_col = next((c for c in ledgers_df.columns if 'name' in c), None)
    if name_col is None:
        logger.warning(f"No recognized name column found in ledgers. Available columns: {list(ledgers_df.columns)}")
        return {}
    try:
        match = ledgers_df[ledgers_df[name_col].astype(str).str.strip().str.lower() == party_name.strip().lower()]
        if match.empty:
            logger.warning(f"Customer '{party_name}' not found in live ledgers (fallback?)")
            return {}
        row = match.iloc[0].to_dict()
        details = {
            'GSTIN': row.get('gstin', '') or row.get('gstin/uin', ''),
            'PAN': row.get('incometaxnumber', '') or row.get('pan', ''),
            'ADDRESS': row.get('address', '') or row.get('mailingname', ''),
            # Add/adjust fields to suit your Tally ledger XML!
        }
        logger.info(f"Enriched customer details for '{party_name}': {details}")
        return details
    except Exception as ex:
        logger.error(f"Failed to lookup customer '{party_name}': {ex}")
        return {}

# Example usage:
if __name__ == "__main__":
    tc = TallyConnector()
    company = "SHREE JI SALES"  # Replace this with your actual company name!
    logger.info("Fetching ledgers...")
    df_ledgers = tc.fetch_ledgers(company)
    logger.info(df_ledgers.head())
