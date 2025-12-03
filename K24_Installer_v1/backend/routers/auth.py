from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime
from backend.database import User, Company, UserSettings, get_db
from backend.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_active_user
)

router = APIRouter(prefix="/auth", tags=["authentication"])

class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str
    company_name: str
    role: str = "admin"  # First user is always admin

class CompanySetup(BaseModel):
    gstin: str | None = None
    pan: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    phone: str | None = None
    tally_company_name: str
    tally_url: str = "http://localhost:9000"
    tally_edu_mode: bool = False
    google_api_key: str | None = None

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    role: str
    company_id: int | None
    
    class Config:
        from_attributes = True

@router.post("/register", response_model=Token)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    # Check if user exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Create company
    company = Company(
        name=user_data.company_name,
        created_at=datetime.now()
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    
    # Create user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        role=user_data.role,
        company_id=company.id,
        is_verified=True,  # Auto-verify first user
        created_at=datetime.now()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create default settings
    settings = UserSettings(user_id=user.id)
    db.add(settings)
    db.commit()
    
    # Create access token
    access_token = create_access_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "company_id": user.company_id
        }
    }

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User account is disabled")
    
    # Update last login
    user.last_login = datetime.now()
    db.commit()
    
    # Create access token
    access_token = create_access_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "company_id": user.company_id
        }
    }

@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    return current_user

@router.post("/setup-company")
def setup_company(
    company_data: CompanySetup,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can setup company")
    
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Update company details
    company.gstin = company_data.gstin
    company.pan = company_data.pan
    company.address = company_data.address
    company.city = company_data.city
    company.state = company_data.state
    company.pincode = company_data.pincode
    company.phone = company_data.phone
    company.tally_company_name = company_data.tally_company_name
    company.tally_url = company_data.tally_url
    company.tally_edu_mode = company_data.tally_edu_mode
    
    # Update user's Google API key
    if company_data.google_api_key:
        current_user.google_api_key = company_data.google_api_key
    
    db.commit()
    
    return {"status": "success", "message": "Company setup completed"}

@router.get("/check-setup")
def check_setup_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    
    setup_complete = bool(
        company and 
        company.tally_company_name and
        company.gstin
    )
    
    return {
        "setup_complete": setup_complete,
        "company": {
            "name": company.name if company else None,
            "gstin": company.gstin if company else None,
            "tally_configured": bool(company and company.tally_company_name)
        } if company else None
    }
