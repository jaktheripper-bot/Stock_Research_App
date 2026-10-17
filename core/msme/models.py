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
        from_attributes = True

"""
SQLAlchemy model (or dataclass fallback) for the `msme_firms` table.
The project currently uses raw SQLite/PostgreSQL connections, but some parts may
import a declarative Base. This file provides both a full SQLAlchemy model (when
Base is available) and a simple dataclass fallback for environments without
SQLAlchemy.
"""

from dataclasses import dataclass


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
