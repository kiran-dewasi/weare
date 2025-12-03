from backend.database import engine, Base, AuditLog
from sqlalchemy import text

def migrate():
    print("Starting Database Migration...")
    
    # 1. Create new tables (AuditLog)
    Base.metadata.create_all(bind=engine)
    print("✅ Created new tables (if missing)")
    
    # 2. Add columns to existing 'vouchers' table
    # SQLite doesn't support IF NOT EXISTS for ADD COLUMN, so we wrap in try/except
    with engine.connect() as conn:
        columns = [
            ("status", "VARCHAR DEFAULT 'Draft'"),
            ("tds_section", "VARCHAR"),
            ("gst_reconciled", "BOOLEAN DEFAULT 0"),
            ("is_backdated", "BOOLEAN DEFAULT 0"),
            ("is_weekend_entry", "BOOLEAN DEFAULT 0")
        ]
        
        for col_name, col_type in columns:
            try:
                conn.execute(text(f"ALTER TABLE vouchers ADD COLUMN {col_name} {col_type}"))
                print(f"✅ Added column: {col_name}")
            except Exception as e:
                if "duplicate column name" in str(e):
                    print(f"ℹ️ Column {col_name} already exists")
                else:
                    print(f"❌ Failed to add {col_name}: {e}")

if __name__ == "__main__":
    migrate()
