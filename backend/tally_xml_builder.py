from typing import Dict, Any, Optional

def build_voucher_xml(
    voucher_type: str, 
    date: str,
    party_ledger: str, 
    amount: float, 
    narration: str = "", 
    voucher_number: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a minimal Sales/Receipt/Payment voucher XML.
    - voucher_type: e.g., "Sales", "Receipt", "Payment", etc.
    - date: YYYYMMDD format string (ex: 20251106)
    - party_ledger: Name of the party ledger in Tally
    - amount: Amount of the voucher (positive for receipt/sales, negative for payment)
    - narration: Optional narration for the voucher
    - voucher_number: Optional voucher number/manual reference
    - extra_fields: Dict of any extra tags/fields for flexibility

    Returns XML string for use with TallyConnector.push_voucher()
    """
    xml = f"""
<VOUCHER>
    <DATE>{date}</DATE>
    <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>
    <PARTYLEDGERNAME>{party_ledger}</PARTYLEDGERNAME>
    <NARRATION>{narration}</NARRATION>
    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{party_ledger}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>{amount:.2f}</AMOUNT>
    </ALLLEDGERENTRIES.LIST>
"""
    if voucher_number:
        xml += f"    <VOUCHERNUMBER>{voucher_number}</VOUCHERNUMBER>\n"
    # Add extra XML tags if provided
    if extra_fields:
        for tag, value in extra_fields.items():
            xml += f"    <{tag}>{value}</{tag}>\n"
    xml += "</VOUCHER>"
    return xml.strip()
