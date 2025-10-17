# models.py
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

Base = declarative_base()
DB_URL = os.getenv("DB_PATH", "sqlite:///./data.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if "sqlite" in DB_URL else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)             # telegram user id
    telegram_id = Column(Integer, unique=True, index=True)
    credits = Column(Integer, default=0)  # represent extra MB allowance (units = MB)
    created_at = Column(DateTime, default=datetime.utcnow)
    apps = relationship("App", back_populates="owner")

class App(Base):
    __tablename__ = "apps"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    repo = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"))
    container_name = Column(String, unique=True)
    mem_mb = Column(Integer, default=256)   # requested memory in MB
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="stopped")
    owner = relationship("User", back_populates="apps")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_id = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Integer)   # rupees or whatever amount
    credits = Column(Integer)  # MB credits to add if approved
    status = Column(String, default="pending") # pending / approved / cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
