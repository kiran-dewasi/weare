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

    # Compliance & Workflow
    status = Column(String, default="Draft")  # Draft, Checked, Verified
    tds_section = Column(String, nullable=True)  # e.g., "194C", "194J"
    gst_reconciled = Column(Boolean, default=False)
    is_backdated = Column(Boolean, default=False)
    is_weekend_entry = Column(Boolean, default=False)

class AuditLog(Base):
    """Immutable Audit Trail for MCA Compliance"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String)  # "Voucher", "Ledger"
    entity_id = Column(String)    # GUID or ID
    user_id = Column(String)      # Who made the change
    action = Column(String)       # "CREATE", "UPDATE", "DELETE"
    timestamp = Column(DateTime, default=datetime.now)
    
    # The "What"
    old_value = Column(String, nullable=True)  # JSON dump
    new_value = Column(String, nullable=True)  # JSON dump
    
    # The "Why"
    reason = Column(String, nullable=False)

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

class Company(Base):
    """Company/Organization details"""
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    gstin = Column(String, nullable=True)
    pan = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    pincode = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    
    # Tally Configuration
    tally_company_name = Column(String, nullable=True)
    tally_url = Column(String, default="http://localhost:9000")
    tally_edu_mode = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)

class User(Base):
    """User accounts with role-based access"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    
    # Role: admin, accountant, auditor, viewer
    role = Column(String, default="accountant")
    
    # Company association
    company_id = Column(Integer, ForeignKey("companies.id"))
    
    # API Keys
    google_api_key = Column(String, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)

class UserSettings(Base):
    """User preferences and settings"""
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # UI Preferences
    theme = Column(String, default="light")  # light, dark
    language = Column(String, default="en")
    
    # Notification Preferences
    email_notifications = Column(Boolean, default=True)
    tally_sync_alerts = Column(Boolean, default=True)
    
    # Feature Flags
    ai_chat_enabled = Column(Boolean, default=True)
    auto_backup = Column(Boolean, default=True)

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
