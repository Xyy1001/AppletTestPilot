from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .element import Element
    from .session import Session
    from .page import Page

from ..clients.vision import vision_client

logger = logging.getLogger(__name__)


class State(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session: Session = Field(exclude=True)
    page: Page
    prev_action: Optional[str] = None
    elements: dict[int, Element] = Field(default_factory=dict)

    def model_post_init(self, __context):
        for e in self.elements.values():
            e.state = self

    @property
    def page_id(self) -> str:
        return self.page.page_id

    @property
    def title(self):
        return self.page.title or self.page.page_id

    @property
    def url(self) -> str:
        return self.page.page_id

    def extract(self, instruction: str, schema: Any) -> Any:
        # Fast path for BaseModel with matching field names
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            lower = (instruction or "").lower()
            field_names = set(getattr(schema, "model_fields", {}).keys())
            if field_names:
                candidate: dict[str, Any] = {}
                if "title" in field_names and ("title" in lower or "page title" in lower):
                    candidate["title"] = self.title
                if "page_id" in field_names and ("page id" in lower or "page_id" in lower or "route" in lower):
                    candidate["page_id"] = self.page_id
                if "url" in field_names and ("url" in lower or "route" in lower or "page id" in lower):
                    candidate["url"] = self.url
                if candidate:
                    try:
                        return schema(**candidate)
                    except Exception:
                        pass

        if schema is str:
            lower = (instruction or "").lower()
            if "title" in lower:
                return self.title
            if "page id" in lower or "page_id" in lower or "route" in lower:
                return self.page.page_id
            return self.title

        screenshot_bytes = self.session.page.screenshot(full_page=True)
        from PIL import Image
        import io
        screenshot = Image.open(io.BytesIO(screenshot_bytes))

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                data = vision_client.extract(screenshot, instruction, schema)
                logger.info(f"Extracted data: {data}")
                return data
            except Exception as e:
                last_error = e
                logger.warning("State extraction failed (attempt %s/3): %s", attempt, e)

        raise last_error if last_error else RuntimeError("State extraction failed")
