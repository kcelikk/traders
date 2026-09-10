"""Duvar saati — yalnızca I/O kenarında enjekte edilir."""
import time


class WallClock:
    def now_ns(self) -> int:
        return time.time_ns()
