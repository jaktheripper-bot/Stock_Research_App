# core/msme/models.py
"""
Pydantic models for MSME firm data.
These models are used for API responses and internal validation.
"""

from typing import Optional
from pydantic import BaseModel, Field

class MsmeFirm(BaseModel):
    """Representation of a MSME firm record.
    All fields correspond to columns in the ``msme_firms`` table.
    """

    uin: str = Field(..., description="Unique Identification Number of the MSME firm")
    name: str = Field(..., description="Registered name of the firm")
    sector_code: Optional[str] = Field(None, description="Sector code as per Ministry classification")
    sector_name: Optional[str] = Field(None, description="Human‑readable sector name")
    city: Optional[str] = Field(None, description="City where the firm is located")
    state: Optional[str] = Field(None, description="State where the firm is located")
    annual_turnover: Optional[float] = Field(None, description="Annual turnover in INR crores (numeric)")
    employee_count: Optional[int] = Field(None, description="Number of employees as reported")
    registration_date: Optional[str] = Field(None, description="Date of registration (ISO string)")
    source: str = Field(..., description="Data source identifier (e.g., 'ministry')")
    last_updated: Optional[str] = Field(None, description="Timestamp of the most recent update")

    class Config:
        orm_mode = True

"""
SQLAlchemy model (or dataclass fallback) for the `msme_firms` table.
The project currently uses raw SQLite/PostgreSQL connections, but some parts may
import a declarative Base. This file provides both a full SQLAlchemy model (when
Base is available) and a simple dataclass fallback for environments without
SQLAlchemy.
"""

from dataclasses import dataclass
from typing import Optional

try:
    # Attempt to import the project's declarative Base if it exists.
    from core.db.models import Base  # type: ignore
    from sqlalchemy import Column, String, Text, Integer, Numeric, Date, DateTime, func

    class MSMEFirm(Base):
        __tablename__ = "msme_firms"

        uin = Column(String, primary_key=True, comment="Unique Identification Number")
        name = Column(Text, nullable=False)
        sector_code = Column(String, nullable=True)
        sector_name = Column(Text, nullable=True)
        city = Column(Text, nullable=True)
        state = Column(Text, nullable=True)
        annual_turnover = Column(Numeric, nullable=True)
        employee_count = Column(Integer, nullable=True)
        registration_date = Column(Date, nullable=True)
        source = Column(String, nullable=False, comment="Data source identifier")
        last_updated = Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
        )
except Exception:  # pragma: no cover – fallback for SQLite‑only environments
    @dataclass
    class MSMEFirm:
        uin: str
        name: str
        sector_code: Optional[str] = None
        sector_name: Optional[str] = None
        city: Optional[str] = None
        state: Optional[str] = None
        annual_turnover: Optional[float] = None
        employee_count: Optional[int] = None
        registration_date: Optional[str] = None
        source: str = "ministry"
        last_updated: Optional[str] = None
