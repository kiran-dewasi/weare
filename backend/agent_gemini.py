# K24 AI Agent - Gemini XML Generator
# ====================================
# Uses Gemini to generate Tally-compliant XML for vouchers
# Integrated with GeminiOrchestrator for robust handling

from typing import Dict, Any, Optional, Tuple, List
import logging
import xml.etree.ElementTree as ET
import os
import re
from datetime import datetime

from backend.gemini.gemini_orchestrator import GeminiOrchestrator

logger = logging.getLogger(__name__)


class XMLGenerationError(Exception):
    """Custom exception for XML generation failures"""
    pass


class GeminiXMLAgent:
    """
    Generates Tally-compliant XML using Gemini.
    Includes schema validation and retry logic.
    """
    
    def __init__(self, api_key: str = None, model_name: str = "gemini-2.0-flash"):
        """Initialize with Gemini Orchestrator"""
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY must be provided")
        
        # Initialize orchestrator with XML-specific system prompt
        self.orchestrator = GeminiOrchestrator(
            api_key=self.api_key,
            system_prompt="You are a Tally XML expert. Output ONLY valid XML."
        )
        print(f"[AGENT] GeminiXMLAgent initialized with model: {model_name}")
    
    async def generate_voucher_xml(
        self,
        voucher_type: str,
        party_name: str,
        amount: float,
        date: str = None,
        narration: str = "",
        additional_params: Dict[str, Any] = None
    ) -> Tuple[bool, str, List[str]]:
        """
        Generate Tally voucher XML.
        Returns: (success, xml_string, errors)
        """
        
        # Normalize inputs
        date = date or datetime.now().strftime("%Y%m%d")
        additional_params = additional_params or {}
        
        # Build prompt
        prompt = self._build_xml_prompt(
            voucher_type=voucher_type,
            party_name=party_name,
            amount=amount,
            date=date,
            narration=narration,
            additional_params=additional_params
        )
        
        try:
            # Generate XML using Orchestrator
            # System prompt is already set in __init__
            response_text = await self.orchestrator.invoke_with_retry(
                query=prompt
            )
            
            # Clean response
            xml_text = self._clean_xml_response(response_text)
            
            # Validate
            is_valid, errors = self._validate_xml(xml_text)
            
            if is_valid:
                logger.info(f"Successfully generated XML for {voucher_type}")
                return (True, xml_text, [])
            else:
                logger.warning(f"Generated XML has validation errors: {errors}")
                
                # Attempt to fix
                logger.info("Attempting to fix XML...")
                return await self.regenerate_with_fixes(xml_text, errors, prompt)
        
        except Exception as e:
            logger.error(f"XML generation failed: {e}")
            return (False, "", [str(e)])
    
    def _build_xml_prompt(
        self,
        voucher_type: str,
        party_name: str,
        amount: float,
        date: str,
        narration: str,
        additional_params: Dict[str, Any]
    ) -> str:
        """Build the Gemini prompt for XML generation"""
        
        # Get deposit account (Cash or Bank)
        deposit_to = additional_params.get("deposit_to", "Cash")
        tax_rate = additional_params.get("tax_rate", 0)
        company_name = additional_params.get("company_name", "Krishasales")
        
        # Calculate tax amount if applicable
        tax_amount = 0
        if tax_rate > 0:
            tax_amount = amount * (tax_rate / 100)
            total_amount = amount + tax_amount
        else:
            total_amount = amount
        
        prompt = f"""You are a Tally XML expert. Generate ONLY valid Tally XML for this voucher.

VOUCHER DETAILS:
- Type: {voucher_type}
- Party Name: {party_name}
- Amount: ₹{amount:.2f}
- {'Tax: ' + str(tax_rate) + '% GST (₹' + str(tax_amount) + ')' if tax_rate > 0 else 'No Tax'}
- {'Total Amount: ₹' + str(total_amount) if tax_rate > 0 else ''}
- Date: {date} (YYYYMMDD format)
- Narration: {narration or 'Created via K24'}
- {'Deposit To: ' + deposit_to if voucher_type in ['Receipt', 'Payment'] else ''}
- Company: {company_name}

STRICT REQUIREMENTS:
1. Use EXACT Tally XML schema for vouchers
2. Format ALL amounts as strings with 2 decimal places (e.g., "50000.00")
3. Use YYYYMMDD date format ONLY
4. Include PROPER ledger entries:
   - For Receipt: Debit {deposit_to}, Credit {party_name}
   - For Payment: Debit {party_name}, Credit {deposit_to}
   - For Sales: Debit {party_name}, Credit Sales Account
5. Use ISDEEMEDPOSITIVE correctly (Yes for debit, No for credit)
6. Include GUID for tracking (generate unique GUID)
7. Ledger names MUST match exactly as provided

XML TEMPLATE STRUCTURE:
<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER ACTION="Create">
            <DATE>{date}</DATE>
            <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>
            <NARRATION>{narration or 'Created via K24'}</NARRATION>
            <ALLLEDGERENTRIES.LIST>
              <!-- First Ledger Entry -->
            </ALLLEDGERENTRIES.LIST>
            <ALLLEDGERENTRIES.LIST>
              <!-- Second Ledger Entry -->
            </ALLLEDGERENTRIES.LIST>
          </VOUCHER>
        </TALLYMESSAGE>
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>

IMPORTANT RULES:
- Amount values MUST be numeric strings with exactly 2 decimal places
- Positive amounts are DEBIT, Negative amounts are CREDIT
- ISDEEMEDPOSITIVE="Yes" means DEBIT side
- ISDEEMEDPOSITIVE="No" means CREDIT side
- Amounts must balance (sum to zero)
- NO explanations, ONLY pure XML
- NO markdown code blocks, ONLY XML
- XML must be valid and well-formed

Generate the complete XML now:"""

        return prompt
    
    def _clean_xml_response(self, xml_text: str) -> str:
        """Clean Gemini response to extract pure XML"""
        
        # Remove markdown code blocks if present
        if "```xml" in xml_text:
            xml_text = xml_text.split("```xml", 1)[1]
            xml_text = xml_text.split("```", 1)[0]
        elif "```" in xml_text:
            xml_text = xml_text.split("```", 1)[1]
            xml_text = xml_text.split("```", 1)[0]
        
        # Remove any explanatory text before <ENVELOPE>
        envelope_match = re.search(r'<ENVELOPE>.*</ENVELOPE>', xml_text, re.DOTALL)
        if envelope_match:
            xml_text = envelope_match.group(0)
        
        # Clean whitespace
        xml_text = xml_text.strip()
        
        return xml_text
    
    def _validate_xml(self, xml_text: str) -> Tuple[bool, List[str]]:
        """
        Validate XML structure and Tally-specific requirements.
        Returns: (is_valid, error_messages)
        """
        errors = []
        
        # Check 1: Valid XML syntax
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            errors.append(f"XML Parse Error: {str(e)}")
            return (False, errors)
        
        # Check 2: Required root elements
        if root.tag != "ENVELOPE":
            errors.append("Root element must be <ENVELOPE>")
        
        header = root.find("HEADER")
        if header is None:
            errors.append("Missing <HEADER> element")
        
        body = root.find("BODY")
        if body is None:
            errors.append("Missing <BODY> element")
            return (False, errors)
        
        # Check 3: IMPORTDATA structure
        importdata = body.find("IMPORTDATA")
        if importdata is None:
            errors.append("Missing <IMPORTDATA> element")
            return (False, errors)
        
        # Check 4: REQUESTDATA and TALLYMESSAGE
        requestdata = importdata.find("REQUESTDATA")
        if requestdata is None:
            errors.append("Missing <REQUESTDATA> element")
            return (False, errors)
        
        tallymessage = requestdata.find("TALLYMESSAGE")
        if tallymessage is None:
            errors.append("Missing <TALLYMESSAGE> element")
            return (False, errors)
        
        # Check 5: VOUCHER element
        voucher = tallymessage.find("VOUCHER")
        if voucher is None:
            errors.append("Missing <VOUCHER> element")
            return (False, errors)
        
        # Check 6: Required voucher fields
        required_fields = ["DATE", "VOUCHERTYPENAME"]
        for field in required_fields:
            if voucher.find(field) is None:
                errors.append(f"Missing required field: <{field}>")
        
        # Check 7: Ledger entries
        ledger_entries = voucher.findall(".//ALLLEDGERENTRIES.LIST")
        if len(ledger_entries) < 2:
            errors.append(f"Need at least 2 ledger entries, found {len(ledger_entries)}")
        
        # Check 8: Amount balancing
        total_amount = 0.0
        for entry in ledger_entries:
            amount_elem = entry.find("AMOUNT")
            if amount_elem is not None and amount_elem.text:
                try:
                    amount = float(amount_elem.text)
                    total_amount += amount
                except ValueError:
                    errors.append(f"Invalid amount format: {amount_elem.text}")
        
        # Amounts should sum to zero (within floating point tolerance)
        if abs(total_amount) > 0.01:
            errors.append(f"Amounts don't balance: total = {total_amount}")
        
        # Check 9: Amount formatting (should have 2 decimal places)
        for entry in ledger_entries:
            amount_elem = entry.find("AMOUNT")
            if amount_elem is not None and amount_elem.text:
                if '.' in amount_elem.text:
                    decimal_part = amount_elem.text.split('.')[1]
                    if len(decimal_part) != 2:
                        errors.append(f"Amount should have exactly 2 decimal places: {amount_elem.text}")
        
        is_valid = len(errors) == 0
        return (is_valid, errors)
    
    async def regenerate_with_fixes(
        self,
        original_xml: str,
        validation_errors: List[str],
        original_prompt: str
    ) -> Tuple[bool, str, List[str]]:
        """
        Attempt to fix XML by asking Gemini to regenerate with error feedback.
        """
        
        fix_prompt = f"""{original_prompt}

PREVIOUS ATTEMPT HAD THESE ERRORS:
{chr(10).join(f"- {error}" for error in validation_errors)}

Fix these errors and generate corrected XML. Remember:
- Amounts must be formatted with exactly 2 decimal places
- All ledger entries must have LEDGERNAME, AMOUNT, ISDEEMEDPOSITIVE
- Amounts must balance to zero
- Use proper Tally schema

Generate the CORRECTED XML now (XML only, no explanations):"""

        try:
            response_text = await self.orchestrator.invoke_with_retry(
                query=fix_prompt
            )
            
            xml_text = self._clean_xml_response(response_text)
            
            is_valid, new_errors = self._validate_xml(xml_text)
            
            return (is_valid, xml_text, new_errors)
        
        except Exception as e:
            logger.error(f"XML regeneration failed: {e}")
            return (False, "", [str(e)])
