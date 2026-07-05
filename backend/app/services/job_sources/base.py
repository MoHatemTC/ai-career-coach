from abc import ABC, abstractmethod
from app.models import JobPosting

class BaseJobSource(ABC):
    """
    Every job source must implement this interface.
    The pipeline only ever calls .fetch() — it doesn't
    care what happens inside.
    """

    source_name: str  # "wuzzuf" | "bayt" | "linkedin" | "fixture"

    @abstractmethod
    async def fetch(self) -> list[JobPosting]:
        """
        Fetch jobs from this source and return them as
        validated JobPosting objects. All field mapping,
        cleaning, and normalization happens inside here.

        Async so sources doing network I/O (e.g. Wuzzuf) can run
        concurrently without blocking the event loop; sources doing only
        local work (e.g. fixtures) simply ``return`` without awaiting.
        """
        raise NotImplementedError
