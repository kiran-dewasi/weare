import xml.etree.ElementTree as ET
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("tally_response_parser")

def parse_tally_response(xml_response: str) -> Dict[str, Any]:
    """
    Parses the raw XML response from Tally and determines success/failure.
    
    Returns a dictionary with:
    - success: bool
    - status: str (e.g., "Success", "Failure", "XML Error")
    - errors: List[str]
    - created: int
    - altered: int
    - deleted: int
    - data: Any (parsed data if applicable)
    """
    result = {
        "success": False,
        "status": "Unknown",
        "errors": [],
        "created": 0,
        "altered": 0,
        "deleted": 0,
        "data": None
    }

    if not xml_response:
        result["errors"].append("Empty response from Tally")
        result["status"] = "Empty Response"
        return result

    try:
        # Clean up potential encoding issues or whitespace
        xml_response = xml_response.strip()
        
        root = ET.fromstring(xml_response)
        
        # 1. Check for LINEERROR (Common Tally Error Tag)
        # Tally errors are often nested deep in the structure
        line_errors = root.findall(".//LINEERROR")
        if line_errors:
            for error in line_errors:
                if error.text:
                    result["errors"].append(error.text.strip())
            
            if result["errors"]:
                result["status"] = "Failure"
                result["success"] = False
                return result

        # 2. Check for Success Counts (CREATED, ALTERED, DELETED)
        # Usually in BODY > IMPORTDATA > RESPONSES
        created = root.find(".//CREATED")
        altered = root.find(".//ALTERED")
        deleted = root.find(".//DELETED")
        errors_count = root.find(".//ERRORS")

        if created is not None: result["created"] = int(created.text or 0)
        if altered is not None: result["altered"] = int(altered.text or 0)
        if deleted is not None: result["deleted"] = int(deleted.text or 0)
        
        # If explicit error count is > 0
        if errors_count is not None and int(errors_count.text or 0) > 0:
             result["success"] = False
             result["status"] = "Failure"
             # If we didn't find LINEERRORs but have error count, add generic message
             if not result["errors"]:
                 result["errors"].append(f"Tally reported {errors_count.text} errors but no details provided.")
             return result

        # 3. Determine Success for Write Operations
        if result["created"] > 0 or result["altered"] > 0 or result["deleted"] > 0:
            result["success"] = True
            result["status"] = "Success"
            return result
        
        # 4. Handle Data Retrieval (Export Data) / Generic Success
        # If no errors found and no specific action counts, it might be a successful fetch or status check.
        # We assume success if we parsed valid XML and found no error indicators.
        if not result["errors"]:
             result["success"] = True
             result["status"] = "Success"
             # We could add logic here to extract data if needed, 
             # but usually fetch_ledgers handles its own parsing.
             # This parser is primarily for Write/Action responses.

    except ET.ParseError as e:
        result["errors"].append(f"XML Parse Error: {str(e)}")
        result["status"] = "XML Error"
        # Include snippet of raw response for debugging
        logger.error(f"Failed to parse XML: {xml_response[:200]}...")
    except Exception as e:
        result["errors"].append(f"Unexpected Error: {str(e)}")
        result["status"] = "System Error"
        logger.exception("Unexpected error in parse_tally_response")

    return result
