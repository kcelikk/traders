"""Çekirdek modüllerinde I/O, saat, rastlantı, ağ import'u yasak (ADR 0007 #1)."""
import ast
from pathlib import Path

FORBIDDEN = {"time", "datetime", "random", "os", "sys", "socket", "http", "urllib", "asyncio", "threading",
             "subprocess", "pathlib", "io", "gzip", "websockets", "requests", "sqlite3", "multiprocessing"}
CORE_FILES = [*Path("fbot/core").glob("*.py"), Path("fbot/costs.py"), Path("fbot/clock.py")]


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
