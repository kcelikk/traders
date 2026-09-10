import pytest

from fbot.core.commands import BarClosed
from fbot.execution.adapter import LiveExecutionAdapter, PaperExecutionAdapter, ReplayExecutionAdapter
from decimal import Decimal

CMD = BarClosed("BTCUSDT", 0, 59999, Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(0), 0)


def test_paper_and_replay_record_commands():
    for A in (PaperExecutionAdapter, ReplayExecutionAdapter):
        a = A()
        a.submit(CMD)
        assert a.submitted == [CMD]


def test_live_adapter_is_guarded_stub():
    a = LiveExecutionAdapter()
    with pytest.raises(RuntimeError, match="onay"):
        a.submit(CMD)
