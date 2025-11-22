"""
K24 Sync Engine
Handles Bi-Directional Sync between Tally and Shadow DB.
"""
import logging
import os
from dotenv import load_dotenv
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import SessionLocal, Ledger, Voucher, StockItem, Bill
from backend.tally_connector import TallyConnector

load_dotenv()
TALLY_URL = os.getenv("TALLY_URL", "http://localhost:9000")

logger = logging.getLogger(__name__)

class SyncEngine:
    def __init__(self):
        self.tally = TallyConnector(url=TALLY_URL)
        
    async def sync_now(self):
        """Trigger a full pull sync from Tally"""
        def log_debug(msg):
            with open("debug_sync.log", "a") as f:
                f.write(f"{datetime.now()} - {msg}\n")
        
        log_debug("Starting Tally Sync...")
        logger.info("Starting Tally Sync...")
        db = SessionLocal()
        try:
            log_debug("Syncing Ledgers...")
            await self._sync_ledgers(db)
            log_debug("Syncing Items...")
            await self._sync_items(db)
            log_debug("Syncing Bills...")
            await self._sync_bills(db)
            log_debug("Syncing Vouchers...")
            await self._sync_vouchers(db)
            db.commit()
            log_debug("Sync Completed Successfully.")
            logger.info("Sync Completed Successfully.")
        except Exception as e:
            log_debug(f"Sync Failed: {e}")
            logger.error(f"Sync Failed: {e}")
            db.rollback()
        finally:
            db.close()

    async def _sync_ledgers(self, db: Session):
        """Fetch Ledgers from Tally and update Shadow DB"""
        try:
            df = self.tally.fetch_ledgers()
            if df.empty:
                logger.warning("No ledgers fetched from Tally.")
                return

            # Normalize columns
            df.columns = [c.lower() for c in df.columns]
            
            count = 0
            for _, row in df.iterrows():
                name = row.get('name', '')
                if not name: continue
                
                ledger = db.query(Ledger).filter(Ledger.name == name).first()
                if not ledger:
                    ledger = Ledger(name=name)
                    db.add(ledger)
                
                ledger.parent = row.get('parent', '')
                # Handle closing balance
                try:
                    ledger.closing_balance = float(row.get('closingbalance', 0))
                except:
                    ledger.closing_balance = 0.0
                    
                ledger.gstin = row.get('gstin', '')
                ledger.last_synced = datetime.now()
                count += 1
                
            logger.info(f"Synced {count} ledgers from Tally.")
        except Exception as e:
            logger.error(f"Error syncing ledgers: {e}")

    async def _sync_items(self, db: Session):
        """Fetch Stock Items from Tally"""
        try:
            df = self.tally.fetch_stock_items()
            if df.empty:
                logger.warning("No stock items fetched from Tally.")
                return

            df.columns = [c.lower() for c in df.columns]
            
            count = 0
            for _, row in df.iterrows():
                name = row.get('name', '')
                if not name: continue

                item = db.query(StockItem).filter(StockItem.name == name).first()
                if not item:
                    item = StockItem(name=name)
                    db.add(item)
                
                try:
                    item.closing_balance = float(row.get('closingbalance', 0))
                    item.rate = float(row.get('standardcost', 0)) # Approximation
                except:
                    pass
                    
                item.last_synced = datetime.now()
                count += 1
                
            logger.info(f"Synced {count} stock items from Tally.")
        except Exception as e:
            logger.error(f"Error syncing items: {e}")

    async def _sync_bills(self, db: Session):
        """Fetch Outstanding Bills"""
        try:
            df = self.tally.fetch_outstanding_bills()
            if df.empty:
                logger.warning("No bills fetched from Tally.")
                return

            df.columns = [c.lower() for c in df.columns]
            
            count = 0
            for _, row in df.iterrows():
                ref = row.get('billref', '')
                if not ref: continue

                bill = db.query(Bill).filter(Bill.bill_name == ref).first()
                if not bill:
                    bill = Bill(bill_name=ref)
                    db.add(bill)
                
                bill.party_name = row.get('partyledgername', '')
                try:
                    bill.amount = float(row.get('openingbalance', 0)) 
                except:
                    bill.amount = 0.0
                    
                bill.last_synced = datetime.now()
                count += 1
                
            logger.info(f"Synced {count} bills from Tally.")
        except Exception as e:
            logger.error(f"Error syncing bills: {e}")

    async def _sync_vouchers(self, db: Session):
        """Fetch Daybook Vouchers"""
        def log_debug(msg):
            with open("debug_sync.log", "a") as f:
                f.write(f"{datetime.now()} - {msg}\n")

        try:
            log_debug("Fetching vouchers from Tally...")
            df = self.tally.fetch_vouchers()
            if df.empty:
                logger.warning("No vouchers fetched from Tally.")
                log_debug("No vouchers fetched")
                return

            # New parser returns: voucher_type, voucher_number, date, narration, party_name, amount
            log_debug(f"Fetched {len(df)} vouchers. Columns: {list(df.columns)}")
            
            count = 0
            for _, row in df.iterrows():
                # Use voucher_number + date as unique identifier
                vch_num = str(row.get('voucher_number', ''))
                vch_date_str = str(row.get('date', ''))
                
                log_debug(f"Processing Voucher: Num={vch_num}, Date={vch_date_str}")
                
                if not vch_num:
                    log_debug("Skipping voucher with no number")
                    continue

                # Parse date string to datetime object
                try:
                    vch_date = datetime.strptime(vch_date_str, '%Y-%m-%d')
                except ValueError:
                    # Fallback if date format is wrong
                    log_debug(f"Invalid date format: {vch_date_str}")
                    vch_date = datetime.now()

                # Try to find existing voucher by number and date
                voucher = db.query(Voucher).filter(
                    Voucher.voucher_number == vch_num,
                    Voucher.date == vch_date
                ).first()
                
                if not voucher:
                    log_debug("Creating NEW voucher")
                    voucher = Voucher()
                    db.add(voucher)
                else:
                    log_debug("Updating EXISTING voucher")
                
                # Map fields from new parser output
                voucher.voucher_number = vch_num
                voucher.voucher_type = row.get('voucher_type', '')
                voucher.party_name = row.get('party_name', '')
                voucher.amount = float(row.get('amount', 0.0))
                voucher.narration = row.get('narration', '')
                voucher.date = vch_date
                voucher.last_synced = datetime.now()
                
                # Generate a temporary GUID if missing (for frontend compatibility)
                if not voucher.guid:
                    voucher.guid = f"TALLY-{vch_num}-{vch_date_str}"
                
                count += 1
                
            logger.info(f"Synced {count} vouchers from Tally.")
            log_debug(f"Successfully synced {count} vouchers")
        except Exception as e:
            logger.error(f"Error syncing vouchers: {e}")
            log_debug(f"Error in _sync_vouchers: {e}")
            import traceback
            with open("debug_sync.log", "a") as f:
                traceback.print_exc(file=f)

    def push_voucher_safe(self, voucher_data: dict) -> dict:
        """
        Transactional Push:
        1. Push to Tally
        2. If Success -> Save to Shadow DB
        3. If Fail -> Return Error (Do not save to DB)
        """
        logger.info(f"Pushing voucher to Tally: {voucher_data}")
        
        # 1. Push to Tally
        tally_response = self.tally.create_voucher(voucher_data)
        
        # 2. Check Tally Response
        if not tally_response.get("status") == "Success":
            logger.error(f"Tally rejected voucher: {tally_response}")
            return {
                "success": False,
                "error": f"Tally Rejected: {tally_response.get('errors', ['Unknown Error'])}",
                "tally_response": tally_response
            }
            
        # 3. Save to Shadow DB (Commit)
        db = SessionLocal()
        try:
            # Create local voucher record
            new_voucher = Voucher(
                voucher_number=voucher_data.get("voucher_number", "AUTO"),
                date=datetime.strptime(voucher_data.get("date", datetime.now().strftime("%Y%m%d")), "%Y%m%d"),
                voucher_type=voucher_data.get("voucher_type"),
                party_name=voucher_data.get("party_name"),
                amount=float(voucher_data.get("amount", 0)),
                narration=voucher_data.get("narration"),
                guid=f"PENDING-{datetime.now().timestamp()}", 
                last_synced=datetime.now()
            )
            db.add(new_voucher)
            db.commit()
            logger.info("Voucher committed to Shadow DB.")
            
            return {
                "success": True,
                "message": "Voucher posted to Tally and saved locally.",
                "tally_response": tally_response
            }
            
        except Exception as e:
            logger.error(f"Shadow DB Commit Failed: {e}")
            db.rollback()
            return {
                "success": True, 
                "message": "Saved to Tally (Local DB sync pending)", 
                "warning": "Local DB update failed"
            }
        finally:
            db.close()

    def undo_voucher_safe(self, voucher_id: int) -> dict:
        """
        Transactional Undo:
        1. Find voucher in Shadow DB
        2. Send DELETE to Tally
        3. If Tally Success -> Delete from Shadow DB
        """
        db = SessionLocal()
        try:
            voucher = db.query(Voucher).filter(Voucher.id == voucher_id).first()
            if not voucher:
                return {"success": False, "error": "Voucher not found in local DB"}
            
            # Construct data for Tally Delete
            voucher_data = {
                "date": voucher.date.strftime("%Y%m%d") if voucher.date else "20240401",
                "voucher_type": voucher.voucher_type,
                "voucher_number": voucher.voucher_number
            }
            
            logger.info(f"Attempting Undo for Voucher {voucher_id}: {voucher_data}")
            
            # 1. Delete from Tally
            tally_response = self.tally.delete_voucher(voucher_data)
            
            if not tally_response.get("success"):
                return {
                    "success": False, 
                    "error": f"Tally Delete Failed: {tally_response.get('errors')}",
                    "tally_response": tally_response
                }
            
            # 2. Delete from Shadow DB
            db.delete(voucher)
            db.commit()
            
            return {
                "success": True,
                "message": "Voucher undone successfully (Deleted from Tally & Local)",
                "tally_response": tally_response
            }
            
        except Exception as e:
            logger.error(f"Undo Failed: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}
        finally:
            db.close()

# Global Sync Instance
sync_engine = SyncEngine()
