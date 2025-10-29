from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Iterable, NamedTuple, Optional
import re
import requests

class Item(NamedTuple):
    code: str
    url: str
    title: Optional[str] = None
    price: Optional[str] = None

class Adapter(ABC):
    @abstractmethod
    def fetch(
        self,
        session: requests.Session,
        url: str,
        include_rx: re.Pattern | None,
        exclude_rx: re.Pattern | None,
    ) -> Iterable[Item]:
        """
        Return an iterable of Items (code, url[, title, price]) currently visible on the list page.
        Implementations should:
          - be idempotent
          - normalize URLs
          - filter by include/exclude regex if provided
        """
        raise NotImplementedError
