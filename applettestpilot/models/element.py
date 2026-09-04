from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .state import State

from ..clients.vision import vision_client

logger = logging.getLogger(__name__)


class Element(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore", populate_by_name=True)

    state: Optional[State] = Field(default=None, exclude=True)

    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0

    visible: bool = True
    text: Optional[str] = ""

    id: int = Field(..., alias="id")
    tag_name: str = Field(..., alias="tagName")
    attributes: dict[str, Any] = Field(default_factory=dict)

    children: list[Element] = Field(default_factory=list, exclude=True)
    parent_id: Optional[int] = Field(None, alias="parentId")
    parent: Optional[Element] = Field(default=None, exclude=True)

    def contains(self, x: float, y: float) -> bool:
        return (
            self.visible
            and self.x <= x <= self.x + self.width
            and self.y <= y <= self.y + self.height
        )

    def extract(self, instruction: str, schema: Any) -> Any:
        if not self.state:
            raise ValueError("Element not attached to State.")

        if schema is str:
            return self.text or ""

        def _get_element_image():
            screenshot_bytes = self.state.session.page.screenshot(full_page=True)
            from PIL import Image
            import io
            image = Image.open(io.BytesIO(screenshot_bytes))
            img_width, img_height = image.size
            x1 = max(0, min(self.x, img_width))
            y1 = max(0, min(self.y, img_height))
            x2 = max(0, min(self.x + self.width, img_width))
            y2 = max(0, min(self.y + self.height, img_height))
            crop_box = (x1, y1, x2, y2)
            return image.crop(crop_box)

        screenshot = _get_element_image()
        element_repr = f"<{self.tag_name} text='{self.text}'>"
        prompt = f"Extract information from the element {element_repr}. Instruction: {instruction}"

        data = vision_client.extract(screenshot, prompt, schema)
        logger.info(f"Extracted data: {data}")
        return data
