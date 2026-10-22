"""
Announcement endpoints for the High School Management System API

Reading active announcements is public; managing them requires a signed-in teacher.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from ..database import announcements_collection, teachers_collection

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    start_date: Optional[date] = None
    expiration_date: date

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be blank")
        return value

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.start_date > self.expiration_date:
            raise ValueError("Start date must not be after expiration date")
        return self


def _require_teacher(teacher_username: Optional[str]) -> None:
    """Raise 401 unless the username belongs to a known teacher."""
    if not teacher_username or not teachers_collection.find_one({"_id": teacher_username}):
        raise HTTPException(
            status_code=401, detail="Authentication required to manage announcements")


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc["_id"],
        "message": doc["message"],
        "start_date": doc.get("start_date"),
        "expiration_date": doc["expiration_date"],
    }


def _to_document(payload: AnnouncementIn) -> Dict[str, Any]:
    return {
        "message": payload.message,
        "start_date": payload.start_date.isoformat() if payload.start_date else None,
        "expiration_date": payload.expiration_date.isoformat(),
    }


@router.get("", response_model=None)
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements that are currently active (public)"""
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [{"start_date": None}, {"start_date": {"$lte": today}}],
    }
    return [_serialize(d) for d in announcements_collection.find(query).sort("expiration_date", 1)]


@router.get("/manage", response_model=None)
def list_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """List all announcements including expired and scheduled ones (auth required)"""
    _require_teacher(teacher_username)
    return [_serialize(d) for d in announcements_collection.find().sort("expiration_date", -1)]


@router.post("", response_model=None)
def create_announcement(payload: AnnouncementIn, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Create an announcement (auth required)"""
    _require_teacher(teacher_username)
    doc = {"_id": str(uuid4()), **_to_document(payload)}
    try:
        announcements_collection.insert_one(doc)
    except Exception:
        logger.exception("Failed to create announcement")
        raise HTTPException(status_code=500, detail="Could not save announcement")
    return _serialize(doc)


@router.put("/{announcement_id}", response_model=None)
def update_announcement(announcement_id: str, payload: AnnouncementIn, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Update an announcement (auth required)"""
    _require_teacher(teacher_username)
    fields = _to_document(payload)
    try:
        result = announcements_collection.update_one(
            {"_id": announcement_id}, {"$set": fields})
    except Exception:
        logger.exception("Failed to update announcement %s", announcement_id)
        raise HTTPException(status_code=500, detail="Could not save announcement")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return _serialize({"_id": announcement_id, **fields})


@router.delete("/{announcement_id}", response_model=None)
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, str]:
    """Delete an announcement (auth required)"""
    _require_teacher(teacher_username)
    try:
        result = announcements_collection.delete_one({"_id": announcement_id})
    except Exception:
        logger.exception("Failed to delete announcement %s", announcement_id)
        raise HTTPException(status_code=500, detail="Could not delete announcement")
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement deleted"}
