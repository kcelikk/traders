"""Paylaşılan test altyapısı.

İki sorunu çözer:
  1. Testlerin birçoğu göreli yol kullanıyor (`Path("tests/fixtures/rec-mini")`,
     `open("fbot/gateway/testnet.py")`). Bu, testlerin yalnızca repo kökünden çalıştırılabilmesi
     demekti. Otomatik `chdir` fixture'ı bu bağımlılığı kaldırır.
  2. Sahte HTTP/WS/user stream nesneleri iki ayrı dosyada kopyalanmıştı. Artık `tests/fake`
     altında tek yerde.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _repo_root_cwd():
    """Testler repo kökünden çalışıyormuş gibi davranır, nereden çağrıldıklarından bağımsız."""
    old = Path.cwd()
    os.chdir(REPO_ROOT)
    yield REPO_ROOT
    os.chdir(old)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fixtures() -> Path:
    return REPO_ROOT / "tests" / "fixtures"
