"""
Invoice Reconciliation Workflow
Autonomous workflow to detect and fix invoice discrepancies
"""
from prefect import flow, task
from typing import Dict, Any, List
import pandas as pd
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from backend.tally_connector import TallyConnector

logger = logging.getLogger(__name__)


@task(name="fetch_ledger_data", retries=2, retry_delay_seconds=5)
def fetch_ledger_entries(party_name: str, company: str, tally_url: str = "http://localhost:9000") -> pd.DataFrame:
    """
    Fetch ledger entries from Tally for the specified party
    
    Args:
        party_name: Name of the party/customer
        company: Tally company name
        tally_url: Tally XML API URL
        
    Returns:
        DataFrame with ledger entries
    """
    try:
        logger.info(f"Fetching ledger entries for {party_name} from company {company}")
        connector = TallyConnector(url=tally_url, company_name=company)
        df = connector.fetch_ledgers_full(company)
        
        # Filter by party name (case-insensitive partial match)
        if 'NAME' in df.columns:
            party_df = df[df['NAME'].str.contains(party_name, case=False, na=False)]
            logger.info(f"Found {len(party_df)} ledger entries for {party_name}")
            return party_df
        else:
            logger.warning("NAME column not found in ledger data")
            return pd.DataFrame()
            
    except Exception as e:
        logger.error(f"Error fetching ledger entries: {e}")
        raise


@task(name="detect_discrepancies")
def detect_discrepancies(df: pd.DataFrame) -> Dict[str, List[Dict]]:
    """
    Detect common issues in ledger entries
    
    Args:
        df: DataFrame with ledger entries
        
    Returns:
        Dictionary of categorized discrepancies
    """
    logger.info(f"Analyzing {len(df)} ledger entries for discrepancies")
    
    discrepancies = {
        "duplicates": [],
        "missing_gstin": [],
        "missing_parent": [],
        "invalid_data": []
    }
    
    if df.empty:
        logger.warning("No data to analyze")
        return discrepancies
    
    # Check for duplicate names
    if 'NAME' in df.columns:
        duplicates = df[df.duplicated(subset=['NAME'], keep=False)]
        if not duplicates.empty:
            discrepancies["duplicates"] = duplicates.to_dict('records')
            logger.info(f"Found {len(duplicates)} duplicate entries")
    
    # Check for missing GSTIN
    if 'GSTIN' in df.columns:
        missing_gstin = df[df['GSTIN'].isna() | (df['GSTIN'] == '')]
        if not missing_gstin.empty:
            discrepancies["missing_gstin"] = missing_gstin.to_dict('records')
            logger.info(f"Found {len(missing_gstin)} entries with missing GSTIN")
    
    # Check for missing PARENT
    if 'PARENT' in df.columns:
        missing_parent = df[df['PARENT'].isna() | (df['PARENT'] == '')]
        if not missing_parent.empty:
            discrepancies["missing_parent"] = missing_parent.to_dict('records')
            logger.info(f"Found {len(missing_parent)} entries with missing PARENT")
    
    total_issues = sum(len(v) for v in discrepancies.values())
    logger.info(f"Total issues detected: {total_issues}")
    
    return discrepancies


@task(name="generate_fixes")
def generate_fixes(discrepancies: Dict[str, List[Dict]]) -> List[Dict[str, Any]]:
    """
    Generate suggested fixes for detected discrepancies
    
    Args:
        discrepancies: Dictionary of categorized issues
        
    Returns:
        List of suggested fixes
    """
    fixes = []
    
    # Generate fixes for missing GSTIN
    for entry in discrepancies.get("missing_gstin", []):
        fixes.append({
            "type": "update",
            "ledger_id": entry.get('ID'),
            "ledger_name": entry.get('NAME'),
            "field": "GSTIN",
            "current_value": entry.get('GSTIN', ''),
            "suggested_value": "PENDING_VERIFICATION",
            "reason": "Missing GSTIN - requires verification",
            "priority": "high"
        })
    
    # Generate fixes for missing PARENT
    for entry in discrepancies.get("missing_parent", []):
        fixes.append({
            "type": "update",
            "ledger_id": entry.get('ID'),
            "ledger_name": entry.get('NAME'),
            "field": "PARENT",
            "current_value": entry.get('PARENT', ''),
            "suggested_value": "Sundry Debtors",  # Default parent group
            "reason": "Missing parent group - defaulting to Sundry Debtors",
            "priority": "high"
        })
    
    # Flag duplicates for manual review
    for entry in discrepancies.get("duplicates", []):
        fixes.append({
            "type": "flag",
            "ledger_id": entry.get('ID'),
            "ledger_name": entry.get('NAME'),
            "reason": "Duplicate entry detected - requires manual review",
            "priority": "medium"
        })
    
    logger.info(f"Generated {len(fixes)} suggested fixes")
    return fixes


@task(name="apply_fixes_to_tally", retries=2, retry_delay_seconds=5)
def apply_fixes_to_tally(
    fixes: List[Dict[str, Any]], 
    company: str,
    tally_url: str,
    enabled: bool = True
) -> Dict[str, Any]:
    """
    Apply approved fixes to Tally
    
    Args:
        fixes: List of fixes to apply
        company: Tally company name
        tally_url: Tally API URL
        enabled: If False, dry-run mode (default: True)
        
    Returns:
        Dictionary with application results
    """
    from backend.tally_live_update import dispatch_tally_update, TallyAPIError
    
    if not enabled:
        logger.info("Dry-run mode: Not applying fixes to Tally")
        return {
            "dry_run": True,
            "total_fixes": len(fixes),
            "message": "Dry-run mode - no changes made to Tally"
        }
    
    results = {
        "applied": [],
        "failed": [],
        "skipped": []
    }
    
    for fix in fixes:
        # Skip flags (manual review needed)
        if fix.get("type") == "flag":
            results["skipped"].append({
                "ledger": fix.get("ledger_name"),
                "reason": fix.get("reason")
            })
            continue
        
        # Apply updates
        if fix.get("type") == "update":
            try:
                # Build update payload for Tally
                updates = {
                    fix["field"]: fix["suggested_value"]
                }
                
                # If updating PARENT, ensure NAME is included
                if fix["field"] == "PARENT":
                    updates["NAME"] = fix["ledger_name"]
                
                logger.info(f"Updating ledger '{fix['ledger_name']}': {updates}")
                
                # Use existing dispatch_tally_update function
                response = dispatch_tally_update(
                    entity_type="ledger",
                    company_name=company,
                    payload={
                        "action": "alter",  # Alter existing ledger
                        "name": fix["ledger_name"],
                        "updates": updates
                    },
                    tally_url=tally_url,
                    timeout=15
                )
                
                results["applied"].append({
                    "ledger": fix["ledger_name"],
                    "field": fix["field"],
                    "value": fix["suggested_value"],
                    "response": response
                })
                logger.info(f"✅ Successfully updated {fix['ledger_name']}")
                
            except TallyAPIError as e:
                logger.error(f"❌ Failed to update {fix['ledger_name']}: {e}")
                results["failed"].append({
                    "ledger": fix["ledger_name"],
                    "error": str(e)
                })
            except Exception as e:
                logger.error(f"❌ Unexpected error updating {fix['ledger_name']}: {e}")
                results["failed"].append({
                    "ledger": fix["ledger_name"],
                    "error": str(e)
                })
    
    total_applied = len(results["applied"])
    total_failed = len(results["failed"])
    total_skipped = len(results["skipped"])
    
    logger.info(f"Applied: {total_applied}, Failed: {total_failed}, Skipped: {total_skipped}")
    
    return {
        "total_fixes": len(fixes),
        "applied": total_applied,
        "failed": total_failed,
        "skipped": total_skipped,
        "details": results
    }



@flow(name="invoice_reconciliation", log_prints=True)
def reconcile_invoices_workflow(
    party_name: str,
    company: str = "SHREE JI SALES",
    tally_url: str = "http://localhost:9000",
    auto_approve: bool = False
) -> Dict[str, Any]:
    """
    Complete invoice reconciliation workflow
    
    Steps:
    1. Fetch ledger entries for party
    2. Detect discrepancies
    3. Generate suggested fixes
    4. (Optional) Wait for approval
    5. Return results
    
    Args:
        party_name: Name of party to reconcile
        company: Tally company name
        tally_url: Tally API URL
        auto_approve: If True, auto-apply fixes (default: False)
        
    Returns:
        Dictionary with workflow results
    """
    print(f"🚀 Starting reconciliation for '{party_name}'...")
    
    # Step 1: Fetch data
    ledger_data = fetch_ledger_entries(party_name, company, tally_url)
    print(f"📊 Found {len(ledger_data)} ledger entries")
    
    if ledger_data.empty:
        return {
            "status": "no_data",
            "party": party_name,
            "message": f"No ledger entries found for '{party_name}'"
        }
    
    # Step 2: Detect issues
    discrepancies = detect_discrepancies(ledger_data)
    total_issues = sum(len(v) for v in discrepancies.values())
    print(f"🔍 Detected {total_issues} potential issues")
    
    # Step 3: Generate fixes
    suggested_fixes = generate_fixes(discrepancies)
    print(f"💡 Generated {len(suggested_fixes)} suggested fixes")
    
    # Step 4: Return results (approval/application will be in next iteration)
    if total_issues == 0:
        return {
            "status": "clean",
            "party": party_name,
            "message": "No issues detected - ledger is clean!",
            "entries_analyzed": len(ledger_data)
        }
    
    if not auto_approve:
        print("⏸️  Awaiting user approval...")
        return {
            "status": "pending_approval",
            "party": party_name,
            "issues_found": total_issues,
            "fixes_suggested": len(suggested_fixes),
            "discrepancies": discrepancies,
            "fixes": suggested_fixes,
            "entries_analyzed": len(ledger_data)
        }
    
    # Step 5: Auto-approve - Apply fixes to Tally
    print("✅ Auto-approval enabled - applying fixes to Tally...")
    
    # Check if Tally live update is enabled
    import os
    tally_live_enabled = os.getenv("TALLY_LIVE_UPDATE_ENABLED", "false").lower() == "true"
    
    application_result = apply_fixes_to_tally(
        fixes=suggested_fixes,
        company=company,
        tally_url=tally_url,
        enabled=tally_live_enabled
    )
    
    print(f"📝 Applied {application_result.get('applied', 0)} fixes, "
          f"Failed {application_result.get('failed', 0)}, "
          f"Skipped {application_result.get('skipped', 0)}")
    
    return {
        "status": "complete",
        "party": party_name,
        "issues_found": total_issues,
        "fixes_applied": application_result.get("applied", 0),
        "fixes_failed": application_result.get("failed", 0),
        "fixes_skipped": application_result.get("skipped", 0),
        "application_details": application_result,
        "message": f"Applied {application_result.get('applied', 0)} fixes to Tally successfully" if tally_live_enabled else "Dry-run mode: no actual changes made"
    }


if __name__ == "__main__":
    # Test the workflow with sample data
    print("Testing invoice reconciliation workflow...")
    result = reconcile_invoices_workflow(
        party_name="Acme Corp",
        company="SHREE JI SALES"
    )
    print("\n" + "="*60)
    print("WORKFLOW RESULT:")
    print("="*60)
    import json
    print(json.dumps(result, indent=2))
