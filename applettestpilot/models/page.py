from typing import Any, Optional
from pydantic import BaseModel


class Page(BaseModel):
    """A logical page within a WeChat Mini Program."""
    page_id: str
    title: Optional[str] = None
    description: str = ""
    layout: Any = None  # minidom Document or similar
