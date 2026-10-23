"""Pydantic schemas for API request/response validation."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Priority = Literal["high", "medium", "low"]
Status = Literal["todo", "done", "missed"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    priority: Priority = "medium"
    deadline: Optional[datetime] = None
    duration_minutes: int = Field(default=30, ge=5, le=600)
    notes: Optional[str] = Field(default=None, max_length=2000)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    priority: Optional[Priority] = None
    deadline: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(default=None, ge=5, le=600)
    status: Optional[Status] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class TaskOut(BaseModel):
    id: str
    title: str
    notes: Optional[str] = None
    priority: Priority
    deadline: Optional[datetime] = None
    duration_minutes: int
    status: Status
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RescheduleRequest(BaseModel):
    new_start: Optional[datetime] = None
    new_deadline: Optional[datetime] = None
    reason: Optional[str] = None


class ScheduleBlockOut(BaseModel):
    id: str
    task_id: str
    start_time: datetime
    end_time: datetime
    kind: Literal["work", "replan"]
    reason: Optional[str] = None
    task_title: Optional[str] = None
    task_priority: Optional[Priority] = None
    task_status: Optional[Status] = None


class GenerateScheduleRequest(BaseModel):
    reason: Optional[str] = None


class ReplanRequest(BaseModel):
    task_ids: Optional[list[str]] = None
    new_deadline: Optional[datetime] = None
    reason: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AgentAction(BaseModel):
    tool: str
    summary: str
    ok: bool = True
    detail: dict = {}


class ChatResponse(BaseModel):
    reply: str
    mode: Literal["bedrock", "mock"]
    actions: list[AgentAction] = []
