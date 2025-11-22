import requests

# Test direct XML request to Tally
tally_url = "http://localhost:9000"

# Request to get all ledgers
xml_request = """<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
<HEADER>
<VERSION>1</VERSION>
<TALLYREQUEST>Export</TALLYREQUEST>
<TYPE>Collection</TYPE>
<ID>List of Ledgers</ID>
</HEADER>
<BODY>
<DESC>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
</STATICVARIABLES>
<TDL>
<TDLMESSAGE>
<COLLECTION NAME="MyLedgers">
<TYPE>Ledger</TYPE>
<FETCH>Name, Parent, ClosingBalance</FETCH>
</COLLECTION>
</TDLMESSAGE>
</TDL>
</DESC>
</BODY>
</ENVELOPE>"""

try:
    response = requests.post(tally_url, data=xml_request, headers={"Content-Type": "text/xml"})
    print("Raw Response (first 2000 chars):")
    print(response.text[:2000])
    print("\n" + "="*60)
    
    # Look for ledger names
    import re
    names = re.findall(r'<NAME>(.*?)</NAME>', response.text)
    print(f"\nFound {len(names)} ledgers:")
    for i, name in enumerate(names[:20]):  # Show first 20
        print(f"{i+1}. {name}")
        
except Exception as e:
    print(f"Error: {e}")
