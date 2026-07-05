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
# 1. DATABASE CONFIGURATION (Secure Env Var)
# ==========================================
# os.environ.get reads the variable from Render's secure settings panel dynamically
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./local_test.db")

# Simple fix for a common SQLAlchemy/PostgreSQL compatibility quirks
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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
# 2. DATABASE TABLES (Updated)
# ==========================================
class DBProvider(Base):
    __tablename__ = "providers"
    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=False)
    phone_number = Column(String, nullable=False)
    location = Column(String, nullable=False)
    is_premium = Column(Boolean, default=False)

class DBService(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    name = Column(String, nullable=False)          # e.g., "Standard Haircut"
    duration_minutes = Column(Integer, nullable=False) # e.g., 40
    price_cash_usd = Column(Float, nullable=False)

class DBAppointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    customer_name = Column(String, nullable=False)
    customer_phone = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)   # Calculated automatically on creation
    status = Column(String, default="Pending")

Base.metadata.create_all(bind=engine)

# ==========================================
# 3. PYDANTIC SCHEMAS (Updated)
# ==========================================
class ProviderCreate(BaseModel):
    business_name: str
    category: str
    phone_number: str
    location: str

class ProviderResponse(ProviderCreate):
    id: int
    is_premium: bool
    class Config: from_attributes = True

class ServiceCreate(BaseModel):
    provider_id: int
    name: str
    duration_minutes: int
    price_cash_usd: float

class ServiceResponse(ServiceCreate):
    id: int
    class Config: from_attributes = True

class AppointmentCreate(BaseModel):
    provider_id: int
    service_id: int
    customer_name: str
    customer_phone: str
    start_time: datetime

class AppointmentResponse(AppointmentCreate):
    id: int
    end_time: datetime
    status: str
    class Config: from_attributes = True

# ==========================================
# 4. HJEZLI APP & API ROUTES
# ==========================================
app = FastAPI(title="Hjezli (حجزلي) API", version="1.0.0")

# --- Provider Endpoints ---
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

# --- Service Endpoints ---
@app.post("/api/services", response_model=ServiceResponse)
def create_service(service: ServiceCreate, db: Session = Depends(get_db)):
    db_service = DBService(**service.model_dump())
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/api/providers/{provider_id}/services", response_model=List[ServiceResponse])
def list_provider_services(provider_id: int, db: Session = Depends(get_db)):
    return db.query(DBService).filter(DBService.provider_id == provider_id).all()

# --- Smart Overlap Protected Appointment Booking ---
@app.post("/api/appointments", response_model=AppointmentResponse)
def create_appointment(appointment: AppointmentCreate, db: Session = Depends(get_db)):
    service = db.query(DBService).filter(DBService.id == appointment.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Selected service does not exist")
    
    req_start = appointment.start_time
    req_end = req_start + timedelta(minutes=service.duration_minutes)
    
    # Anti-overbooking query
    overlapping_booking = db.query(DBAppointment).filter(
        DBAppointment.provider_id == appointment.provider_id,
        DBAppointment.status.in_(["Pending", "Confirmed"]),
        DBAppointment.start_time < req_end,
        DBAppointment.end_time > req_start
    ).first()
    
    if overlapping_booking:
        raise HTTPException(
            status_code=400, 
            detail=f"Time slot conflict! This provider is fully booked from {overlapping_booking.start_time.strftime('%H:%M')} to {overlapping_booking.end_time.strftime('%H:%M')}."
        )
    
    db_appointment = DBAppointment(
        provider_id=appointment.provider_id,
        service_id=appointment.service_id,
        customer_name=appointment.customer_name,
        customer_phone=appointment.customer_phone,
        start_time=req_start,
        end_time=req_end,
        status="Pending"
    )
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

