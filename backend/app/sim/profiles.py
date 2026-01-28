from __future__ import annotations

from dataclasses import dataclass
import random

@dataclass(frozen=True)
class SimProfile:
    name: str
    events_per_min_low: int
    events_per_min_high: int

    def sample_rate_per_min(self) -> int:
        return random.randint(self.events_per_min_low, self.events_per_min_high)

PROFILES: dict[str, SimProfile] = {
    "quiet": SimProfile("quiet", 0, 1),
    "normal": SimProfile("normal", 2, 8),
    "busy": SimProfile("busy", 10, 30),
}
