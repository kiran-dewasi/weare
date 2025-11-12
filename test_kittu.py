import requests
import json
import logging
import sys

# ----------- CONFIGURATION -----------
API_BASE = "http://localhost:8000"  # Update if your API runs elsewhere

ENDPOINTS = {
    "import_xml": "/import-tally/",
    "agent_query": "/ask-agent/",
    "modify_data": "/modify/",
    "get_customer_details": "/customer-details/",
    "list_ledgers": "/list-ledgers/"
}

SAMPLE_XML = "sample_tally.xml"
TEST_QUESTION = "Give me all overdue bills for company Acme Corp."
MODIFY_RECORD_ID = 123
DEFAULT_UPDATES = {"status": "paid", "amount": 5000}
CUSTOMER_NAME = "Acme Corp"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KittuTestScript")

# ----------- TEST FUNCTIONS -----------
def read_xml_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Could not read XML: {e}")
        sys.exit(1)

def get_index_by_id(record_id):
    resp = requests.get(API_BASE + ENDPOINTS["list_ledgers"]) \
        if ENDPOINTS.get("list_ledgers") else None
    if not resp or not resp.ok:
        return None
    payload = resp.json()
    rows = payload.get("rows") or []
    # Try matching on common ID keys
    for idx, row in enumerate(rows):
        if ("ID" in row and str(row["ID"]) == str(record_id)) or ("id" in row and str(row["id"]) == str(record_id)):
            return idx
    return None

def test_import_tally_xml(xml_path):
    xml_data = read_xml_file(xml_path)
    resp = requests.post(API_BASE + ENDPOINTS["import_xml"], json={"xml_input": xml_data})
    print("\n[Import XML] Response:")
    print(json.dumps(resp.json(), indent=2))
    assert resp.ok, "API did not return OK for import"
    return resp.json()

def test_agent_query(question):
    resp = requests.post(API_BASE + ENDPOINTS["agent_query"], json={"query": question})
    print("\n[Agent Q&A] Response:")
    print(json.dumps(resp.json(), indent=2))
    assert resp.ok, "API did not return OK for agent query"
    return resp.json()

def test_data_modification(record_id, updates):
    idx = get_index_by_id(record_id)
    if idx is None:
        print(f"\n[Modify Data] Could not find idx for record_id={record_id}")
        idx = 0  # fallback to first row to keep test moving
    modify_payload = {
        "action": "update",
        "data": updates,
        "idx": idx
    }
    resp = requests.post(API_BASE + ENDPOINTS["modify_data"], json=modify_payload)
    print("\n[Modify Data] Payload:")
    print(json.dumps(modify_payload, indent=2))
    print("[Modify Data] Response:")
    print(json.dumps(resp.json(), indent=2))
    assert resp.ok, "API did not return OK for modification"
    return resp.json()

def test_data_deletion(record_id):
    idx = get_index_by_id(record_id)
    if idx is None:
        print(f"\n[Delete Data] Could not find idx for record_id={record_id}")
        idx = 0  # fallback to first row
    delete_payload = {
        "action": "delete",
        "data": {},
        "idx": idx
    }
    resp = requests.post(API_BASE + ENDPOINTS["modify_data"], json=delete_payload)
    print("\n[Delete Data] Payload:")
    print(json.dumps(delete_payload, indent=2))
    print("[Delete Data] Response:")
    print(json.dumps(resp.json(), indent=2))
    assert resp.ok, "API did not return OK for deletion"
    return resp.json()

def test_customer_details(customer_name):
    resp = requests.post(API_BASE + ENDPOINTS["get_customer_details"], json={"name": customer_name})
    print("\n[Customer Details] Response:")
    print(json.dumps(resp.json(), indent=2))
    assert resp.ok, "API did not return OK for customer details"
    return resp.json()

def test_customer_edge_cases():
    test_names = [" acme corp ", "ACME CORP", "acme corp", "Nonexistent Co"]
    for name in test_names:
        resp = requests.post(API_BASE + ENDPOINTS["get_customer_details"], json={"name": name})
        print(f"\n[Customer Lookup: '{name}'] Response:")
        print(json.dumps(resp.json(), indent=2))
        assert resp.ok, "API did not return OK for customer lookup"

def test_modify_nonexistent():
    modify_payload = {
        "action": "update",
        "data": {"status": "paid"},
        "idx": 999999
    }
    resp = requests.post(API_BASE + ENDPOINTS["modify_data"], json=modify_payload)
    print("\n[Modify Non-existent Record] Payload:")
    print(json.dumps(modify_payload, indent=2))
    print("[Modify Non-existent Record] Response:")
    print(json.dumps(resp.json(), indent=2))
    assert resp.ok, "API did not return OK for modifying non-existent"

def test_broken_xml():
    # Purposefully invalid XML string
    bad_xml = "<root><data></root"
    resp = requests.post(API_BASE + ENDPOINTS["import_xml"], json={"xml_input": bad_xml})
    print("\n[Broken XML Import] Response (should error gracefully):")
    print(json.dumps(resp.json(), indent=2))
    assert resp.ok, "API did not return OK on broken XML (should provide error feedback)"
    return resp.json()

def test_list_data():
    resp = requests.get(API_BASE + ENDPOINTS["list_ledgers"])
    print("\n[List Ledgers] Status Code:", resp.status_code)
    if not resp.ok:
        print("[List Ledgers] Error Response Text:", resp.text)
    try:
        data = resp.json()
        print("[List Ledgers] Response:")
        print(json.dumps(data, indent=2))
        assert resp.ok, "API did not return OK for listing"
        return data
    except json.JSONDecodeError as e:
        print(f"[List Ledgers] JSON Decode Error: {e}")
        print("[List Ledgers] Raw Response Text:", resp.text[:500])
        raise

def test_full_agent_pipeline():
    xml_data = read_xml_file(SAMPLE_XML)
    import_resp = requests.post(API_BASE + ENDPOINTS["import_xml"], json={"xml_input": xml_data}).json()
    # Try to extract first record's id
    first_record_id = None
    rows = None
    if import_resp.get('data') and 'rows' in import_resp['data'] and import_resp['data']['rows']:
        rows = import_resp['data']['rows']
    elif import_resp.get('rows') and isinstance(import_resp['rows'], list) and import_resp['rows']:
        rows = import_resp['rows']
    if rows:
        # Derive record id from common key variants
        first = rows[0]
        first_record_id = first.get('ID') or first.get('id')
    if first_record_id:
        # Agent Q&A before modification
        q_resp = requests.post(API_BASE + ENDPOINTS["agent_query"], json={"query": TEST_QUESTION}).json()
        print("\n[Agent Q&A - Pre Modification] Response:", json.dumps(q_resp, indent=2))
        # Modify the record via idx mapping
        test_data_modification(first_record_id, {"status": "paid"})
        # Agent Q&A after modification
        verify_resp = requests.post(API_BASE + ENDPOINTS["agent_query"], json={"query": TEST_QUESTION}).json()
        print("\n[Agent Q&A - Post Modification] Response:", json.dumps(verify_resp, indent=2))
    else:
        print("No records available to chain-test.")

def test_api_robustness():
    # Malformed JSON
    bad_json = '{"xml_input": "<root></root>'  # missing closing quote/brace
    resp = requests.post(API_BASE + ENDPOINTS["import_xml"], data=bad_json, headers={"Content-Type": "application/json"})
    print("\n[Malformed JSON] Response:", resp.text)
    # Wrong content type
    resp = requests.post(API_BASE + ENDPOINTS["import_xml"], data="<root></root>", headers={"Content-Type": "text/plain"})
    print("\n[Wrong Content-Type] Response:", resp.text)
    # Missing required field
    resp = requests.post(API_BASE + ENDPOINTS["import_xml"], json={})
    print("\n[Missing Field] Response:", resp.text)

# ----------- RUN TEST SUITE -----------
if __name__ == "__main__":
    print("\n======= Kittu System End-to-End Test =======")

    # 1. Test XML Import and Parsing
    import_response = test_import_tally_xml(SAMPLE_XML)

    # 2. Test Agent Q&A Endpoint
    agent_response = test_agent_query(TEST_QUESTION)

    # 3. Test Data Modification Endpoint (using ID->idx mapping)
    mod_response = test_data_modification(MODIFY_RECORD_ID, DEFAULT_UPDATES)

    # 4. Test Data Deletion (using ID->idx mapping)
    delete_response = test_data_deletion(MODIFY_RECORD_ID)

    # 5. Test Customer Detail Lookup
    cust_response = test_customer_details(CUSTOMER_NAME)

    # 6. Test Customer Lookup Edge Cases
    test_customer_edge_cases()

    # 7. Test Modify Non-existent Record
    test_modify_nonexistent()

    # 8. Test List Ledgers Endpoint
    list_response = test_list_data()

    # 9. Robustness: Test Invalid/Broken XML
    broken_response = test_broken_xml()

    # 10. Test Full Agent Pipeline (import, agent Q, modify, agent Q)
    test_full_agent_pipeline()

    # 11. API Robustness error scenarios
    test_api_robustness()

    print("\n======= All tests completed! Manual inspection of output is recommended for best coverage. =======")
