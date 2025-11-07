from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import NamedTuple

import requests


class Item(NamedTuple):
    code: str
    url: str
    title: str | None = None
    price: str | None = None

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
