"""
K24 Sync Engine
Handles Bi-Directional Sync between Tally and Shadow DB.
"""
import logging
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import SessionLocal, Ledger, Voucher
from backend.tally_connector import TallyConnector

logger = logging.getLogger(__name__)

class SyncEngine:
    def __init__(self):
        self.tally = TallyConnector()
        
    async def sync_now(self):
        """Trigger a full pull sync from Tally"""
        logger.info("Starting Tally Sync...")
        db = SessionLocal()
        try:
            await self._sync_ledgers(db)
            # await self._sync_vouchers(db) # TODO: Implement Voucher Sync
            db.commit()
            logger.info("Sync Completed Successfully.")
        except Exception as e:
            logger.error(f"Sync Failed: {e}")
            db.rollback()
        finally:
            db.close()

    async def _sync_ledgers(self, db: Session):
        """Fetch Ledgers from Tally and update Shadow DB"""
        # 1. Fetch XML from Tally
        # Note: In a real app, we'd fetch the full list. 
        # For MVP, we'll use the sample data or a specific TDL query.
        # Here we simulate fetching/parsing for demonstration.
        
        # Simulating Tally Response
        tally_ledgers = [
            {"name": "Vasudev Enterprises", "parent": "Sundry Debtors", "balance": 15000.0, "gstin": "24ABCDE1234F1Z5"},
            {"name": "Sharma Trading Co", "parent": "Sundry Debtors", "balance": 5000.0, "gstin": "24XYZAB1234F1Z5"},
            {"name": "Acme Corp", "parent": "Sundry Creditors", "balance": -20000.0, "gstin": "27AAAAA0000A1Z5"}
        ]
        
        for data in tally_ledgers:
            # Check if exists
            ledger = db.query(Ledger).filter(Ledger.name == data['name']).first()
            if not ledger:
                ledger = Ledger(name=data['name'])
                db.add(ledger)
            
            # Update fields
            ledger.parent = data['parent']
            ledger.closing_balance = data['balance']
            ledger.gstin = data['gstin']
            ledger.last_synced = datetime.now()
            
        logger.info(f"Synced {len(tally_ledgers)} ledgers.")

# Global Sync Instance
sync_engine = SyncEngine()
