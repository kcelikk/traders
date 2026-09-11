"""Konsol görünüm önbelleği: yeniden başlatmada 24 saatlik kaydı baştan oynatmasın.

Kural: önbellek yalnızca **manifestte kapanmış** dosyalardan sonra yazılır ve yüklenirken
uyumluluğu doğrulanır. Uyumsuz ya da bozuk önbellek sessizce atlanır, kayıt baştan oynatılır —
yanlış duruma devam etmektense yeniden hesaplamak doğrudur.
"""
import gzip
import json
import pickle
import threading
from pathlib import Path

from fbot.api.live_view import LiveView
from fbot.api.server import Tailer, ViewCache

FIX = Path("tests/fixtures/rec-mini")


def run_dir(tmp_path, n_files=2):
    src = next(FIX.glob("events-*.jsonl.gz"))
    lines = gzip.open(src, "rb").read().splitlines(keepends=True)
    d = tmp_path / "rec"; d.mkdir()
    per = len(lines) // n_files
    names = []
    for i in range(n_files):
        name = f"events-20260910T080{i}-{i + 1}.jsonl.gz"
        chunk = lines[i * per:] if i == n_files - 1 else lines[i * per:(i + 1) * per]
        with gzip.open(d / name, "wb") as f:       # kapatılmazsa gzip trailer yazılmaz, dosya kesik sayılır
            f.write(b"".join(chunk))
        names.append(name)
    (d / "manifest.jsonl").write_text("".join(json.dumps({"file": n}) + "\n" for n in names))
    return d, names


def view_of(symbols=("BTCUSDT",)):
    return LiveView(list(symbols), W=10, N_short=2, N_long=3)


def tail_once(d, cache_dir, symbols=("BTCUSDT",)):
    """Tailer'ı tek geçişte çalıştırır (arka plan döngüsü olmadan)."""
    v = view_of(symbols)
    t = Tailer(d, v, threading.Lock(), history_files=10, cache=ViewCache(cache_dir, symbols=list(symbols), key="k1"))
    t.replay_history()
    return t, v


def test_second_start_reads_from_cache_instead_of_replaying(tmp_path):
    d, names = run_dir(tmp_path, n_files=3)
    cache = tmp_path / "cache"
    t1, v1 = tail_once(d, cache)
    assert t1.lines > 0 and t1.from_cache == 0          # ilk açılış: baştan oynatır
    t2, v2 = tail_once(d, cache)
    assert t2.from_cache == t1.lines                     # ikinci açılış: hepsi önbellekten
    assert t2.lines == t1.lines
    assert v2.snapshot(0)["recorder"]["seq"] == v1.snapshot(0)["recorder"]["seq"]


def test_new_closed_file_is_replayed_on_top_of_the_cache(tmp_path):
    """Önbellek sonrası gelen kapanmış dosya oynatılır; önceki dosyalar tekrar okunmaz."""
    d, names = run_dir(tmp_path, n_files=2)
    cache = tmp_path / "cache"
    t1, _ = tail_once(d, cache)                          # 1. dosya oynatıldı, önbelleğe yazıldı
    src = next(FIX.glob("events-*.jsonl.gz"))
    extra = "events-20260910T0802-3.jsonl.gz"
    with gzip.open(d / extra, "wb") as f:
        f.write(gzip.open(src, "rb").read())
    (d / "manifest.jsonl").write_text("".join(json.dumps({"file": n}) + "\n" for n in names + [extra]))
    t2, _ = tail_once(d, cache)
    assert t2.from_cache == t1.lines and t2.lines > t1.lines


def test_resumed_view_matches_a_full_replay(tmp_path):
    d, _ = run_dir(tmp_path, n_files=3)
    cache = tmp_path / "cache"
    _, full = tail_once(d, tmp_path / "bos")
    tail_once(d, cache)                       # önbelleği doldur
    _, resumed = tail_once(d, cache)
    a, b = full.snapshot(0), resumed.snapshot(0)
    assert a["universe"] == b["universe"] and a["state_counts"] == b["state_counts"]
    assert a["recorder"]["events"] == b["recorder"]["events"]


def test_corrupt_cache_is_ignored(tmp_path):
    d, _ = run_dir(tmp_path)
    cache = tmp_path / "cache"
    tail_once(d, cache)
    next(cache.glob("*.pkl")).write_bytes(b"bu pickle degil")
    t, _ = tail_once(d, cache)
    assert t.from_cache == 0 and t.lines > 0


def test_cache_from_a_different_symbol_set_is_ignored(tmp_path):
    """Evren ya da feature ayarı değişmişse eski görünüm kullanılamaz."""
    d, _ = run_dir(tmp_path)
    cache = tmp_path / "cache"
    tail_once(d, cache, symbols=("BTCUSDT",))
    t, _ = tail_once(d, cache, symbols=("BTCUSDT", "ETHUSDT"))
    assert t.from_cache == 0


def test_cache_pointing_at_a_missing_file_is_ignored(tmp_path):
    d, names = run_dir(tmp_path)
    cache = tmp_path / "cache"
    tail_once(d, cache)
    blob = pickle.loads(next(cache.glob("*.pkl")).read_bytes())
    blob["after_file"] = "events-yok-boyle-bir-dosya.jsonl.gz"
    next(cache.glob("*.pkl")).write_bytes(pickle.dumps(blob))
    t, _ = tail_once(d, cache)
    assert t.from_cache == 0


def test_open_file_is_never_cached(tmp_path):
    """Manifestte olmayan (hâlâ yazılan) dosyadan sonra önbellek yazılmaz."""
    d, names = run_dir(tmp_path)
    (d / "manifest.jsonl").write_text(json.dumps({"file": names[0]}) + "\n")   # ikincisi açık
    cache = tmp_path / "cache"
    tail_once(d, cache)
    blob = pickle.loads(next(cache.glob("*.pkl")).read_bytes())
    assert blob["after_file"] == names[0]


def test_api_wires_the_cache_and_reports_cached_lines(tmp_path):
    """Konsol açılışta önbellekten kaç satır aldığını /api/state'te bildirir."""
    from fbot.api.server import Api
    d, _ = run_dir(tmp_path, n_files=3)
    cache = tmp_path / "cache"
    a1 = Api(d, Path("ui"), history_files=10, cache_dir=cache)
    a1.tailer.replay_history()
    assert a1.state()["tail_from_cache"] == 0 and a1.tailer.lines > 0
    a2 = Api(d, Path("ui"), history_files=10, cache_dir=cache)
    a2.tailer.replay_history()
    assert a2.state()["tail_from_cache"] == a1.tailer.lines


def test_cache_can_be_disabled(tmp_path):
    from fbot.api.server import Api
    d, _ = run_dir(tmp_path, n_files=2)
    api = Api(d, Path("ui"), history_files=10, cache_dir=None)
    assert api.tailer.cache is None
    api.tailer.replay_history()
    assert api.tailer.from_cache == 0
