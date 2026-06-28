import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# ==========================================
# 1. DATABASE CONFIGURATION (SQLAlchemy)
# ==========================================
#DATABASE_URL = "YOUR_SUPABASE_CONNECTION_STRING"  # <-- Make sure your working string is here!
DATABASE_URL = "postgresql://postgres.iyezlolfsvezzvzispto:ABdallah_11sqlpass@aws-1-eu-central-1.pooler.supabase.com:6543/postgres"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 2. DATABASE TABLES (PostgreSQL Schema)
# ==========================================
class DBProvider(Base):
    __tablename__ = "providers"
    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=False)
    phone_number = Column(String, nullable=False)
    location = Column(String, nullable=False)
    is_premium = Column(Boolean, default=False)

class DBAppointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    customer_name = Column(String, nullable=False)
    customer_phone = Column(String, nullable=False)
    appointment_time = Column(DateTime, nullable=False)
    price_cash_usd = Column(Float, nullable=False)
    status = Column(String, default="Pending")

Base.metadata.create_all(bind=engine)

# ==========================================
# 3. PYDANTIC SCHEMAS (Data Validation)
# ==========================================
class ProviderCreate(BaseModel):
    business_name: str
    category: str
    phone_number: str
    location: str

class ProviderResponse(ProviderCreate):
    id: int
    is_premium: bool
    class Config:
        from_attributes = True

class AppointmentCreate(BaseModel):
    provider_id: int
    customer_name: str
    customer_phone: str
    appointment_time: datetime
    price_cash_usd: float

class AppointmentResponse(AppointmentCreate):
    id: int
    status: str
    class Config:
        from_attributes = True

# ==========================================
# 4. HJEZLI APP & API ROUTES
# ==========================================
app = FastAPI(title="Hjezli (حجزلي) API", version="1.0.0")

@app.post("/api/providers", response_model=ProviderResponse)
def register_provider(provider: ProviderCreate, db: Session = Depends(get_db)):
    db_provider = DBProvider(**provider.model_dump())
    db.add(db_provider)
    db.commit()
    db.refresh(db_provider)
    return db_provider

@app.get("/api/providers", response_model=List[ProviderResponse])
def list_providers(category: Optional[str] = None, location: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(DBProvider)
    if category:
        query = query.filter(DBProvider.category == category)
    if location:
        query = query.filter(DBProvider.location == location)
    return query.all()

@app.post("/api/appointments", response_model=AppointmentResponse)
def create_appointment(appointment: AppointmentCreate, db: Session = Depends(get_db)):
    provider = db.query(DBProvider).filter(DBProvider.id == appointment.provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    db_appointment = DBAppointment(**appointment.model_dump())
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    return db_appointment

@app.get("/api/providers/{provider_id}/appointments", response_model=List[AppointmentResponse])
def get_provider_appointments(provider_id: int, db: Session = Depends(get_db)):
    return db.query(DBAppointment).filter(DBAppointment.provider_id == provider_id).all()

@app.patch("/api/appointments/{appointment_id}")
def update_appointment_status(appointment_id: int, status: str, db: Session = Depends(get_db)):
    appointment = db.query(DBAppointment).filter(DBAppointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if status not in ["Confirmed", "Cancelled", "Completed"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    appointment.status = status
    db.commit()
    return {"message": f"Appointment status updated to {status}"}

# ==========================================
# 5. SERVE FRONTEND TEMPLATES
# ==========================================
@app.get("/", response_class=HTMLResponse)
def read_customer_ui():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/provider", response_class=HTMLResponse)
def read_provider_ui():
    with open("templates/provider.html", "r", encoding="utf-8") as f:
        return f.read()