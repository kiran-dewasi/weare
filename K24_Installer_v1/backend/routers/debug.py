from fastapi import APIRouter, Depends
from backend.api import get_api_key
from backend.tally_connector import TallyConnector
import logging

router = APIRouter(prefix="/debug", tags=["debug"])
logger = logging.getLogger(__name__)

@router.get("/tally-test")
async def test_tally_connection():
    """
    Comprehensive Tally connectivity and voucher creation test.
    Returns detailed diagnostics to identify the exact issue.
    """
    results = {
        "tests": [],
        "overall_status": "unknown"
    }
    
    try:
        tally = TallyConnector()
        
        # Test 1: Connection
        try:
            ledgers_df = tally.fetch_ledgers()
            results["tests"].append({
                "name": "Connection to Tally",
                "status": "PASS",
                "details": f"Fetched {len(ledgers_df)} ledgers"
            })
        except Exception as e:
            results["tests"].append({
                "name": "Connection to Tally",
                "status": "FAIL",
                "error": str(e)
            })
            results["overall_status"] = "FAIL - Cannot connect to Tally"
            return results
        
        # Test 2: Check if Cash ledger exists
        try:
            cash_lookup = tally.lookup_ledger("Cash")
            results["tests"].append({
                "name": "Cash Ledger Lookup",
                "status": "PASS" if cash_lookup else "WARN",
                "details": f"Found: {cash_lookup}" if cash_lookup else "Cash ledger not found"
            })
        except Exception as e:
            results["tests"].append({
                "name": "Cash Ledger Lookup",
                "status": "ERROR",
                "error": str(e)
            })
        
        # Test 3: Try to create a test ledger
        try:
            test_ledger_result = tally.create_ledger_if_missing("K24_TEST_CUSTOMER", "Sundry Debtors")
            results["tests"].append({
                "name": "Create Test Ledger",
                "status": "PASS" if test_ledger_result.get("success") else "FAIL",
                "details": test_ledger_result
            })
        except Exception as e:
            results["tests"].append({
                "name": "Create Test Ledger",
                "status": "ERROR",
                "error": str(e)
            })
        
        # Test 4: Try to create a minimal Receipt voucher
        try:
            from datetime import datetime
            current_date = datetime.now().strftime("%Y%m01")  # Current month, day 01
            
            voucher_data = {
                "voucher_type": "Receipt",
                "date": current_date,
                "party_name": "K24_TEST_CUSTOMER",
                "amount": 100.0,
                "narration": "K24 Diagnostic Test Receipt",
                "deposit_to": "Cash"
            }
            
            voucher_result = tally.create_voucher(voucher_data)
            
            results["tests"].append({
                "name": "Create Test Receipt Voucher",
                "status": "PASS" if voucher_result.get("status") == "Success" else "FAIL",
                "details": voucher_result,
                "raw_xml_response": voucher_result.get("raw", "")[:500]  # First 500 chars
            })
            
            if voucher_result.get("status") != "Success":
                results["overall_status"] = "FAIL - Voucher Creation Failed"
                results["root_cause"] = voucher_result.get("raw", "Unknown")
            else:
                results["overall_status"] = "PASS"
                
        except Exception as e:
            results["tests"].append({
                "name": "Create Test Receipt Voucher",
                "status": "ERROR",
                "error": str(e),
                "traceback": "Check backend logs"
            })
            results["overall_status"] = "FAIL - Exception during voucher creation"
        
        return results
        
    except Exception as e:
        return {
            "overall_status": "CRITICAL ERROR",
            "error": str(e),
            "tests": results.get("tests", [])
        }
