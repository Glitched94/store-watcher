from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Pattern

import requests


@dataclass(slots=True)
class Item:
    code: str
    url: str
    title: Optional[str] = None
    price: Optional[str] = None
    image: Optional[str] = None
    available: Optional[bool] = None
    availability: Optional[str] = None


class Adapter:
    """
    Simple adapter base. Implement `fetch(session, url, include_rx, exclude_rx) -> Iterable[Item]`.
    """

    def fetch(  # pragma: no cover - interface
        self,
        session: requests.Session,
        url: str,
        include_rx: Optional[Pattern[str]],
        exclude_rx: Optional[Pattern[str]],
    ) -> Iterable[Item]:
        raise NotImplementedError
