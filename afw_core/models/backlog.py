from pydantic import BaseModel


class BacklogOutput(BaseModel):
    epic_count: int
    story_count: int
    description: str
