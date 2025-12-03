from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import json
from backend.tally_connector import TallyConnector

router = APIRouter(prefix="/setup", tags=["setup"])

CONFIG_FILE = "k24_config.json"

class SetupRequest(BaseModel):
    tally_url: str
    company_name: str
    google_api_key: str = ""

@router.get("/status")
async def get_setup_status():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            return {"configured": True, "config": config}
        except:
            return {"configured": False}
    return {"configured": False}

@router.post("/connect")
async def test_connection(request: SetupRequest):
    try:
        connector = TallyConnector(url=request.tally_url, company_name=request.company_name)
        # Try to fetch ledgers (limit 1) to verify connection
        df = connector.fetch_ledgers()
        if df.empty:
             # It might be empty if no ledgers, but usually there are default ones.
             # If connection failed, it would raise exception.
             pass
        
        return {"success": True, "message": f"Successfully connected to {request.company_name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")

@router.post("/save")
async def save_config(request: SetupRequest):
    # Test first
    await test_connection(request)
    
    config = {
        "tally_url": request.tally_url,
        "company_name": request.company_name,
        "google_api_key": request.google_api_key,
        "setup_completed": True
    }
    
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)
        
    return {"success": True}
