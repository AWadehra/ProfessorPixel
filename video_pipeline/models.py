"""Pydantic models for storyboard and scene validation."""

from pydantic import BaseModel, Field


class Scene(BaseModel):
    scene_number: int
    duration_seconds: int = 8
    veo_prompt: str = Field(min_length=10)
    narration: str = Field(min_length=5)
    visual_description: str


class Storyboard(BaseModel):
    title: str = Field(min_length=1)
    scenes: list[Scene] = Field(min_length=1)
