"""ui/index.html üretimi: tasarım kaynağı değişmez, şablondaki her bağlama mantıkta karşılık bulur.

JS çalıştıran bir motor yok; bu yüzden mantık dosyası yapısal olarak denetlenir (dizge/yorum
farkındalıklı parantez dengesi) ve şablon bağlamaları adla eşleştirilir.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from scripts.build_ui import DESIGN, UI, build, template

# Uzaktaki tasarımla bayt-eş; değişirse yapı betiğindeki yerine koymalar gözden geçirilmeli
DESIGN_SHA256 = "1ddf01a4cf46a8d505adb408dc14be2b15abff93214d4224cb222f739b34d735"

OPEN, CLOSE = "([{", ")]}"
PAIR = {")": "(", "]": "[", "}": "{"}
REGEX_PREV = set("(,=:[!&|?{};+-*%~^\n\t ")


def balance(src: str) -> list[str]:
    """Dizge, şablon dizgesi, yorum ve regex literallerini atlayarak parantez dengesini denetler."""
    stack, i, n, prev = [], 0, len(src), ""
    while i < n:
        c = src[i]
        if c in "'\"":
            i += 1
            while i < n and src[i] != c:
                i += 2 if src[i] == "\\" else 1
            i += 1
            prev = c
            continue
        if c == "`":
            i += 1
            while i < n and src[i] != "`":
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                    depth, i = 1, i + 2
                    while i < n and depth:
                        if src[i] in "([{":
                            depth += 1
                        elif src[i] in ")]}":
                            depth -= 1
                        i += 1
                    continue
                i += 1
            i += 1
            prev = "`"
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            i = src.find("\n", i) + 1 or n
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i = src.find("*/", i) + 2
            continue
        if c == "/" and prev in REGEX_PREV:
            i += 1
            while i < n and src[i] != "/":
                i += 2 if src[i] == "\\" else 1
            i += 1
            prev = "/"
            continue
        if c in OPEN:
            stack.append((c, i))
        elif c in CLOSE:
            if not stack or stack[-1][0] != PAIR[c]:
                return [f"{i} konumunda eşleşmeyen {c!r}"]
            stack.pop()
        if not c.isspace():
            prev = c
        elif c == "\n":
            prev = "\n"
        i += 1
    return [f"kapanmamış {c!r} (konum {p})" for c, p in stack]


def test_design_source_is_never_modified():
    assert hashlib.sha256(DESIGN.read_bytes()).hexdigest() == DESIGN_SHA256


def scripts_in(html: str) -> list[str]:
    return re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)


def test_logic_and_panels_are_structurally_balanced():
    for name in ("console-logic.html", "keys-panel.html"):
        bodies = scripts_in((UI / name).read_text())
        assert bodies, name
        for i, body in enumerate(bodies):
            assert balance(body) == [], f"{name} · script {i}"


def test_index_html_is_up_to_date():
    assert (UI / "index.html").read_text() == build(), "ui/index.html eski — `make ui-build`"


def test_every_template_binding_exists_in_logic():
    tpl = template(DESIGN.read_text())
    logic = (UI / "console-logic.html").read_text()
    aliases = set(re.findall(r'as="([A-Za-z_]\w*)"', tpl)) | {"true", "false", "null"}
    names = {m.split(".")[0] for m in re.findall(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}", tpl)}
    missing = sorted(n for n in names - aliases if not re.search(rf"(?<![\w.]){re.escape(n)}\s*[:,]", logic))
    assert missing == [], f"şablonda var, mantıkta yok: {missing}"


def test_history_screen_is_inserted_once():
    out = build()
    assert out.count('<sc-if value="{{ isHistory }}"') == 1
    assert out.count("</x-dc>") == 1 and out.count("<x-dc>") == 1


def declarations_and_params(body: str) -> tuple[dict, set]:
    """Maskelenmiş gövdeden `const`/`let` bildirimleri ve ok fonksiyonu parametreleri."""
    decls: dict[str, int] = {}
    for mo in re.finditer(r"\b(?:const|let)\s+([A-Za-z_$][\w$]*)", body):
        decls.setdefault(mo.group(1), mo.start(1))
    params = set()
    for mo in re.finditer(r"(?:\(([^()]*)\)|([A-Za-z_$][\w$]*))\s*=>", body):
        for part in (mo.group(1) or mo.group(2) or "").split(","):
            part = part.strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                params.add(part)
    return decls, params


def mask_strings(src: str) -> str:
    """Dizge ve satır yorumlarını boşlukla değiştirir; kimlik taraması metne takılmasın."""
    out, i, n = list(src), 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"`":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            for k in range(i, min(j + 1, n)):
                out[k] = " "
            i = j + 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


def test_no_use_before_declaration_in_render():
    """`const` bildiriminden önce kullanım tarayıcıda ReferenceError verir (RC hatası böyle çıktı)."""
    src = (UI / "console-logic.html").read_text()
    body = src[src.index("renderVals() {"):]
    masked = mask_strings(body)
    decls, params = declarations_and_params(masked)
    bad = []
    for name, pos in decls.items():
        if name in params:
            continue
        use = re.search(rf"(?<![\w$.]){re.escape(name)}(?![\w$])", masked)
        if use and use.start() < pos:
            bad.append(f"{name} (kullanım satır {body[:use.start()].count(chr(10)) + 1}, bildirim satır {body[:pos].count(chr(10)) + 1})")
    assert bad == [], "bildirimden önce kullanım: " + ", ".join(sorted(bad))
