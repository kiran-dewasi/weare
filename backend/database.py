"""
K24 Shadow Database
The high-speed local store that mirrors Tally.
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

# SQLite for MVP (File-based, fast, easy to backup)
DATABASE_URL = "sqlite:///./k24_shadow.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Ledger(Base):
    """Mirrors a Tally Ledger"""
    __tablename__ = "ledgers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    parent = Column(String)
    opening_balance = Column(Float, default=0.0)
    closing_balance = Column(Float, default=0.0)
    gstin = Column(String, nullable=True)
    email = Column(String, nullable=True)
    
    # Sync Status
    last_synced = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)

class Voucher(Base):
    """Mirrors a Tally Voucher (Sales/Purchase)"""
    __tablename__ = "vouchers"
    
    id = Column(Integer, primary_key=True, index=True)
    guid = Column(String, unique=True, index=True) # Tally's GUID
    voucher_number = Column(String)
    date = Column(DateTime)
    voucher_type = Column(String) # Sales, Purchase, Receipt, Payment
    party_name = Column(String, ForeignKey("ledgers.name"))
    amount = Column(Float)
    narration = Column(String, nullable=True)
    
    # Sync Status
    sync_status = Column(String, default="SYNCED") # SYNCED, PENDING, ERROR
    last_synced = Column(DateTime, default=datetime.now)

class StockItem(Base):
    """Mirrors Tally Stock Item"""
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    parent = Column(String, nullable=True)
    closing_balance = Column(Float, default=0.0) # Quantity
    rate = Column(Float, default=0.0) # Last known rate
    units = Column(String, default="Nos")
    
    last_synced = Column(DateTime, default=datetime.now)

class Bill(Base):
    """Mirrors Outstanding Bills (Receivables/Payables)"""
    __tablename__ = "bills"
    
    id = Column(Integer, primary_key=True, index=True)
    bill_name = Column(String, index=True) # Ref No
    party_name = Column(String, ForeignKey("ledgers.name"))
    amount = Column(Float) # Positive = Receivable, Negative = Payable
    due_date = Column(DateTime, nullable=True)
    is_overdue = Column(Boolean, default=False)
    
    last_synced = Column(DateTime, default=datetime.now)

def init_db():
    """Create tables"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
