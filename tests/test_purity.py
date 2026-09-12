"""Çekirdek modüllerinde I/O, saat, rastlantı, ağ import'u yasak (ADR 0007 #1)."""
import ast
from pathlib import Path

FORBIDDEN = {"time", "datetime", "random", "os", "sys", "socket", "http", "urllib", "asyncio", "threading",
             "subprocess", "pathlib", "io", "gzip", "websockets", "requests", "sqlite3", "multiprocessing",
             "logging", "secrets", "uuid"}
# rglob: Gate 4'te `fbot/core/reactors/`, Gate 5'te `fbot/strategy/` alt paketleri otomatik kapsanır
CORE_FILES = [*Path("fbot/core").rglob("*.py"), *Path("fbot/strategy").rglob("*.py"),
              Path("fbot/costs.py"), Path("fbot/clock.py")]


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def test_core_modules_exist():
    assert Path("fbot/core/engine.py").exists() and Path("fbot/costs.py").exists() and Path("fbot/clock.py").exists()


def test_core_has_no_forbidden_imports():
    for f in CORE_FILES:
        bad = imports_of(f) & FORBIDDEN
        assert not bad, f"{f}: yasak import {bad}"


def test_core_does_not_import_io_edges():
    for f in CORE_FILES:
        mods = {m for m in imports_of(f)}
        src = f.read_text()
        assert "fbot.gateway" not in src and "fbot.recorder" not in src and "fbot.replay" not in src, f


def test_core_never_reads_the_wall_clock_by_attribute():
    """`import time` yasak ama `from time import monotonic_ns` ya da bir yardımcıdan sızan
    saat erişimi AST import taramasına yakalanmaz. İsim erişimini de tara."""
    bad = []
    for f in CORE_FILES:
        src = f.read_text()
        for needle in ("time.time", "time.monotonic", "perf_counter", "datetime.now", "utcnow"):
            if needle in src:
                bad.append(f"{f}: {needle}")
    assert bad == [], "çekirdekte duvar saati erişimi: " + ", ".join(bad)


def test_core_does_not_iterate_unordered_sets_when_building_commands():
    """Sırasız iterasyon determinizmi bozar. Çekirdekte `for ... in <set>` görünüyorsa
    `sorted()` ile sarılmalı. Heuristik ama ucuz ve gerçek bir hatayı yakalar."""
    import re
    bad = []
    for f in CORE_FILES:
        for i, line in enumerate(f.read_text().splitlines(), 1):
            m = re.search(r"for\s+\w+\s+in\s+(\w+)\.(active_algos|pending_entries)\b", line)
            if m and "sorted(" not in line:
                bad.append(f"{f}:{i}")
    assert bad == [], "sıralanmamış set iterasyonu: " + ", ".join(bad)
