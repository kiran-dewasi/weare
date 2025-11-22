import requests
import xml.etree.ElementTree as ET
import pandas as pd
from typing import Optional, Dict, Any
from xml.sax.saxutils import escape
import logging
import os
from backend.tally_response_parser import parse_tally_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tally_connector")

TALLY_API_URL = os.getenv("TALLY_URL", "http://localhost:9000")
DEFAULT_COMPANY = os.getenv("TALLY_COMPANY", "SHREE JI SALES")

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

def push_to_tally(xml_data):
    """
    Legacy wrapper for backward compatibility.
    Uses TallyConnector to push XML and returns raw response text on success, None on failure.
    """
    connector = TallyConnector()
    result = connector.push_xml(xml_data)
    if result["success"]:
        # Return a success indicator or the raw response if available?
        # Original returned response.text.
        # We can reconstruct a simple success XML or just return "OK"
        return "<RESPONSE>Success</RESPONSE>"
    else:
        logger.error(f"Push failed: {result['errors']}")
        return None

class TallyConnector:
    """
    Connector for TallyPrime XML-HTTP interface.
    Supports reading ledgers/vouchers and pushing updates directly to Tally.
    """
    def __init__(self, url: str = TALLY_API_URL, timeout: int = 15, company_name: Optional[str] = None):
        self.url = url
        self.timeout = timeout
        self.company_name = company_name or DEFAULT_COMPANY

    def send_request(self, xml: str) -> str:
        """
        Sends raw XML to Tally and returns raw text response.
        Raises RuntimeError on HTTP connection issues.
        """
        headers = {"Content-Type": "application/xml"}
        try:
            # Ensure XML is encoded properly
            resp = requests.post(self.url, data=xml.encode("utf-8"), headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.error(f"Tally HTTP Request failed: {e}")
            raise RuntimeError(f"TallyConnector HTTP error: {e}")

    def push_xml(self, xml: str) -> Dict[str, Any]:
        """
        Sends XML to Tally and returns a robustly parsed response dictionary.
        Use this for all WRITE operations (Create/Alter/Delete).
        """
        try:
            raw_response = self.send_request(xml)
            return parse_tally_response(raw_response)
        except RuntimeError as e:
            return {
                "success": False,
                "status": "Connection Error",
                "errors": [str(e)],
                "created": 0, "altered": 0, "deleted": 0, "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "status": "Unexpected Error",
                "errors": [str(e)],
                "created": 0, "altered": 0, "deleted": 0, "data": None
            }

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
        try:
            xml_response = self.send_request(xml)
            return self._parse_ledger_xml(xml_response)
        except Exception as e:
            logger.error(f"Failed to fetch ledgers: {e}")
            return pd.DataFrame()

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

    def fetch_stock_items(self, company_name: Optional[str] = None) -> pd.DataFrame:
        cname = company_name or self.company_name
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
            <BODY>
                <EXPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>List of StockItems</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{escape(cname)}</SVCURRENTCOMPANY>
                        </STATICVARIABLES>
                    </REQUESTDESC>
                </EXPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        return self._parse_generic_xml(xml_response, "STOCKITEM")

    def fetch_outstanding_bills(self, company_name: Optional[str] = None) -> pd.DataFrame:
        cname = company_name or self.company_name
        xml = f"""
        <ENVELOPE>
            <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
            <BODY>
                <EXPORTDATA>
                    <REQUESTDESC>
                        <REPORTNAME>Bills Outstanding</REPORTNAME>
                        <STATICVARIABLES>
                            <SVCURRENTCOMPANY>{escape(cname)}</SVCURRENTCOMPANY>
                        </STATICVARIABLES>
                    </REQUESTDESC>
                </EXPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        xml_response = self.send_request(xml)
        return self._parse_generic_xml(xml_response, "BILL")

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
        logger.info(f"Tally fetch_vouchers response size: {len(xml_response)} bytes")
        if len(xml_response) < 500:
            logger.info(f"Response preview: {xml_response}")
        
        df = self._parse_voucher_xml(xml_response)
        logger.info(f"Parsed {len(df)} vouchers from response")
        return df

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

    def create_voucher(self, voucher_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates a voucher in Tally using the XML Import feature.
        Expects voucher_data to contain:
        - voucher_type: str (Sales, Purchase, Receipt, Payment)
        - date: str (YYYYMMDD)
        - party_name: str
        - amount: float
        - narration: str (optional)
        - items: List[Dict] (optional, for inventory vouchers)
          - name: str
          - quantity: float
          - rate: float
          - amount: float
        """
        cname = self.company_name or "SHREE JI SALES" # Fallback
        
        # Basic XML construction (simplified for MVP)
        # In a real app, use a proper XML builder library
        
        items_xml = ""
        if "items" in voucher_data and voucher_data["items"]:
            for item in voucher_data["items"]:
                items_xml += f"""
                <ALLINVENTORYENTRIES.LIST>
                    <STOCKITEMNAME>{escape(item['name'])}</STOCKITEMNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <RATE>{item['rate']}</RATE>
                    <AMOUNT>{-abs(item['amount'])}</AMOUNT> <!-- Credit for Sales -->
                    <ACTUALQTY>{item['quantity']}</ACTUALQTY>
                    <BILLEDQTY>{item['quantity']}</BILLEDQTY>
                </ALLINVENTORYENTRIES.LIST>
                """

        # Ledger entries (Party + Sales/Purchase Account)
        # Assuming Sales for now
        is_sales = voucher_data.get("voucher_type", "Sales") == "Sales"
        party_amount = -abs(voucher_data['amount']) if is_sales else abs(voucher_data['amount'])
        sales_amount = abs(voucher_data['amount']) if is_sales else -abs(voucher_data['amount'])
        
        ledger_entries_xml = f"""
        <LEDGERENTRIES.LIST>
            <LEDGERNAME>{escape(voucher_data['party_name'])}</LEDGERNAME>
            <ISDEEMEDPOSITIVE>{'Yes' if is_sales else 'No'}</ISDEEMEDPOSITIVE>
            <AMOUNT>{party_amount}</AMOUNT>
        </LEDGERENTRIES.LIST>
        <LEDGERENTRIES.LIST>
            <LEDGERNAME>Sales</LEDGERNAME> <!-- Hardcoded Sales Ledger for MVP -->
            <ISDEEMEDPOSITIVE>{'No' if is_sales else 'Yes'}</ISDEEMEDPOSITIVE>
            <AMOUNT>{sales_amount}</AMOUNT>
        </LEDGERENTRIES.LIST>
        """

        # Tally Edu Mode Handling
        # Edu mode only allows dates 1, 2, 31.
        # If enabled, we force the date to the 1st of the month to ensure acceptance.
        is_edu_mode = os.getenv("TALLY_EDU_MODE", "true").lower() == "true"
        voucher_date = voucher_data.get('date', '20240401')
        
        if is_edu_mode:
            # Simple logic: keep YYYYMM but set DD to 01
            # Input format expected: YYYYMMDD
            if len(voucher_date) == 8:
                original_date = voucher_date
                voucher_date = voucher_date[:6] + "01"
                if original_date != voucher_date:
                    logger.warning(f"Edu Mode: Adjusted voucher date from {original_date} to {voucher_date}")

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
                        <TALLYMESSAGE xmlns:UDF="TallyUDF">
                            <VOUCHER VCHTYPE="{escape(voucher_data['voucher_type'])}" ACTION="Create" OBJVIEW="Invoice Voucher View">
                                <DATE>{voucher_date}</DATE>
                                <VOUCHERTYPENAME>{escape(voucher_data['voucher_type'])}</VOUCHERTYPENAME>
                                <PARTYLEDGERNAME>{escape(voucher_data['party_name'])}</PARTYLEDGERNAME>
                                <NARRATION>{escape(voucher_data.get('narration', 'Created via K24'))}</NARRATION>
                                <FBTPAYMENTTYPE>Default</FBTPAYMENTTYPE>
                                <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
                                {items_xml}
                                {ledger_entries_xml}
                            </VOUCHER>
                        </TALLYMESSAGE>
                    </REQUESTDATA>
                </IMPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        
        logger.info(f"Pushing Voucher XML to Tally: {xml}")
        xml_response = self.send_request(xml)
        return {"status": self._parse_response_status(xml_response), "raw": xml_response}

    def delete_voucher(self, voucher_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deletes a voucher in Tally.
        Requires identifying info (Date, VoucherType, VoucherNumber or MasterID).
        For simplicity in this MVP, we try to match by Date + VchType + VchNo if available,
        or we might need the GUID if we stored it.
        """
        cname = self.company_name or DEFAULT_COMPANY
        
        # To delete, we need to identify the voucher. 
        # Tally deletion usually requires the exact original ID (GUID/MasterId) or the composite key.
        # Here we assume we have the GUID or we construct the same key.
        
        # If we have a GUID/MasterID, it's best.
        # Otherwise, we try to delete by VchNo + Date + Type
        
        date_val = voucher_data.get('date', '20240401')
        vch_type = voucher_data.get('voucher_type', 'Sales')
        vch_no = voucher_data.get('voucher_number')
        
        # Tally Delete XML
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
                        <TALLYMESSAGE xmlns:UDF="TallyUDF">
                            <VOUCHER VCHTYPE="{escape(vch_type)}" ACTION="Delete" OBJVIEW="Invoice Voucher View">
                                <DATE>{date_val}</DATE>
                                <VOUCHERTYPENAME>{escape(vch_type)}</VOUCHERTYPENAME>
                                <VOUCHERNUMBER>{escape(vch_no)}</VOUCHERNUMBER>
                                <!-- If we had GUID/MasterID, we'd put it here -->
                            </VOUCHER>
                        </TALLYMESSAGE>
                    </REQUESTDATA>
                </IMPORTDATA>
            </BODY>
        </ENVELOPE>
        """
        return self.push_xml(xml)

    @staticmethod
    def _parse_ledger_xml(xml_text: str) -> pd.DataFrame:
        try:
            # Sanitize before parsing
            xml_text = TallyConnector._sanitize_xml(xml_text)
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
    def _sanitize_xml(xml_text: str) -> str:
        """
        Robustly sanitize XML from Tally.
        1. Removes invalid XML 1.0 characters (control chars).
        2. Fixes common Tally issues like unescaped ampersands or invalid entities.
        """
        import re
        
        # 1. Remove invalid XML 1.0 characters
        # Valid: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
        # We construct a regex to MATCH INVALID characters and replace them
        # Note: We keep \t, \n, \r
        xml_text = re.sub(r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\u10000-\u10FFFF]', '', xml_text)

        # 2. Handle specific Tally garbage like &#x4; which is invalid in XML 1.0
        # This regex finds numeric entities that resolve to invalid chars
        def replace_entity(match):
            try:
                # Get the number
                ent = match.group(1)
                if ent.startswith('x'):
                    val = int(ent[1:], 16)
                else:
                    val = int(ent)
                # Check if valid
                if (val == 0x9 or val == 0xA or val == 0xD or 
                    (0x20 <= val <= 0xD7FF) or 
                    (0xE000 <= val <= 0xFFFD) or 
                    (0x10000 <= val <= 0x10FFFF)):
                    return match.group(0) # Keep valid
                return '' # Remove invalid
            except:
                return match.group(0)

        xml_text = re.sub(r'&#(x?[0-9a-fA-F]+);', replace_entity, xml_text)
        
        return xml_text

    @staticmethod
    def _parse_voucher_xml(xml_text: str) -> pd.DataFrame:
        """
        Parse Tally voucher XML and extract meaningful voucher data.
        Handles nested ALLLEDGERENTRIES.LIST structure properly.
        """
        try:
            # Sanitize before parsing
            xml_text = TallyConnector._sanitize_xml(xml_text)
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logging.error(f"XML ParseError: {e}")
            logging.error(f"First 2000 chars: {xml_text[:2000]}")
            return pd.DataFrame()
        
        rows = []
        
        # Find all TALLYMESSAGE tags (Tally 9+ format)
        for tallymessage in root.iter("TALLYMESSAGE"):
            for voucher in tallymessage.findall("VOUCHER"):
                voucher_data = TallyConnector._extract_voucher_data(voucher)
                if voucher_data:
                    rows.append(voucher_data)
        
        # If no TALLYMESSAGE found, try direct VOUCHER tags (older format)
        if not rows:
            for voucher in root.iter("VOUCHER"):
                voucher_data = TallyConnector._extract_voucher_data(voucher)
                if voucher_data:
                    rows.append(voucher_data)
        
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    
    @staticmethod
    def _extract_voucher_data(voucher_elem) -> dict:
        """
        Extract structured data from a single VOUCHER element.
        Returns a dictionary with voucher details.
        """
        data = {}
        
        # Get voucher type from attributes
        data['voucher_type'] = voucher_elem.attrib.get('VCHTYPE', '')
        
        # Get voucher number
        vch_num = voucher_elem.find('VOUCHERNUMBER')
        data['voucher_number'] = vch_num.text if vch_num is not None and vch_num.text else ''
        
        # Get date and parse it (format: YYYYMMDD)
        date_elem = voucher_elem.find('DATE')
        if date_elem is not None and date_elem.text:
            date_str = date_elem.text
            try:
                # Parse YYYYMMDD format
                from datetime import datetime
                data['date'] = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
            except:
                data['date'] = date_str
        else:
            data['date'] = ''
        
        # Get narration
        narration = voucher_elem.find('NARRATION')
        data['narration'] = narration.text if narration is not None and narration.text else ''
        
        # Extract ledger entries
        ledger_entries = voucher_elem.findall('.//ALLLEDGERENTRIES.LIST')
        
        # For simplicity, we'll extract the first party ledger and total amount
        party_name = ''
        total_amount = 0.0
        
        for ledger in ledger_entries:
            ledger_name_elem = ledger.find('LEDGERNAME')
            amount_elem = ledger.find('AMOUNT')
            
            if ledger_name_elem is not None and ledger_name_elem.text:
                ledger_name = ledger_name_elem.text
                
                # Get amount
                if amount_elem is not None and amount_elem.text:
                    try:
                        amount = float(amount_elem.text)
                        # Use the positive amount as the voucher amount
                        if abs(amount) > abs(total_amount):
                            total_amount = abs(amount)
                            # Set party name to the ledger with the larger amount
                            party_name = ledger_name
                    except ValueError:
                        pass
        
        data['party_name'] = party_name
        data['amount'] = total_amount
        
        return data

    @staticmethod
    def _parse_generic_xml(xml_text: str, tag_name: str) -> pd.DataFrame:
        try:
            # Sanitize before parsing
            xml_text = TallyConnector._sanitize_xml(xml_text)
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logging.error(f"XML ParseError: {e}")
            return pd.DataFrame()
        rows = []
        for item in root.iter(tag_name):
            data = flatten_element(item)
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
