"""ui/index.html üretir: tasarım şablonu + konsol mantığı + ek paneller.

`ui/design/fbot Console.dc.html` **değiştirilmez**; uzaktaki tasarımla bayt-eş kalır.
Şablonda düzeltilmesi gereken sabit metinler burada, gerekçesiyle birlikte, açık listede tutulur.
Her yerine koyma tam bir kez uygulanmak zorundadır; uygulanmazsa yapı hata verir (tasarım
güncellenince sessizce bozulmasın).

Kullanım: python -m scripts.build_ui [--check]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"
DESIGN = UI / "design" / "fbot Console.dc.html"

HEAD = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>window.__resources = {
  "https://unpkg.com/react@18.3.1/umd/react.production.min.js": "./vendor/react.production.min.js",
  "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js": "./vendor/react-dom.production.min.js",
  "https://unpkg.com/@babel/standalone@7.29.0/babel.min.js": "./vendor/babel.min.js"
};</script>
<title>fbot Console</title>
<script src="./support.js"></script>
</head>
<body>
"""

# Dar ekran (F13): satır içi stil media query ile ezilemez, bu yüzden üç kapsayıcıya sınıf verilir.
RESPONSIVE_CSS = """    @media (max-width: 900px) {
      .fbot-layout { grid-template-columns:minmax(0,1fr) !important; }
      .fbot-aside { flex-direction:row !important; flex-wrap:wrap !important; border-right:0 !important; border-bottom:1px solid #1a2536 !important; padding:8px !important; }
      .fbot-aside > button { width:auto !important; }
      .fbot-aside > div { margin-top:0 !important; width:100%; }
      .fbot-main { padding:12px !important; }
      .fbot-main table { font-size:10px !important; }
    }
    @media (max-width: 560px) {
      .fbot-main h1 { font-size:18px !important; }
    }
"""

OVERRIDES = [
    ("dar ekran: yerleşim sınıfları (F13)",
     '<div style="display:grid; grid-template-columns:200px minmax(0,1fr); min-height:0; min-width:0;">',
     '<div class="fbot-layout" style="display:grid; grid-template-columns:200px minmax(0,1fr); min-height:0; min-width:0;">'),
    ("dar ekran: yan menü sınıfı (F13)",
     '<aside style="border-right:1px solid #1a2536;',
     '<aside class="fbot-aside" style="border-right:1px solid #1a2536;'),
    ("dar ekran: ana alan sınıfı (F13)",
     '<main style="padding:20px 24px;',
     '<main class="fbot-main" style="padding:20px 24px;'),
    ("dar ekran: media query",
     "    @keyframes flowDash { to{stroke-dashoffset:-24} }\n",
     "    @keyframes flowDash { to{stroke-dashoffset:-24} }\n" + RESPONSIVE_CSS),
    ("güvenlik rozetleri doğrulanmadan yeşil gösteriliyordu (F03)",
     '<div style="display:flex; gap:6px; flex-wrap:wrap; font-size:11px;"><span style="border:1px solid #00e5a0; color:#00e5a0; padding:2px 8px;">çekim yetkisi kapalı</span><span style="border:1px solid #00e5a0; color:#00e5a0; padding:2px 8px;">IP whitelist</span><span style="border:1px solid #1a2536; color:#6f849c; padding:2px 8px;">Ed25519 session.logon · Faz 9</span><span style="border:1px solid #1a2536; color:#6f849c; padding:2px 8px;">.env gitignore</span></div>',
     '<div style="display:flex; gap:6px; flex-wrap:wrap; font-size:11px;"><sc-for list="{{ securityChips }}" as="s" hint-placeholder-count="4"><span style="{{ s.style }}">{{ s.text }}</span></sc-for></div>'),
    ("sistemde var olup konsolda izlenmeyen parçalar açıkça listelenir",
     '<div style="font-size:10px; letter-spacing:.14em; color:#6f849c; margin-top:10px;">GÜVENLİK</div>',
     '<div style="font-size:10px; letter-spacing:.14em; color:#6f849c; margin-top:10px;">SİSTEM BAĞLANTI DURUMU</div>'
     '<sc-for list="{{ wiring }}" as="w" hint-placeholder-count="5">'
     '<div style="display:flex; gap:10px; font-size:11px; padding:3px 0; border-bottom:1px solid #111a28;">'
     '<span style="color:#9fb0c3; min-width:170px;">{{ w.k }}</span><span style="{{ w.style }}">{{ w.v }}</span></div>'
     '</sc-for>'
     '<div style="font-size:10px; letter-spacing:.14em; color:#6f849c; margin-top:10px;">GÜVENLİK</div>'),
    ("eşik notu artık koşunun kendi config'inden okunuyor (F02)",
     '<div style="font-size:10px; color:#6f849c;">Eşikler başlangıç değeri; 72 saatlik kayıttan sonra ölçümle güncellenir.</div>',
     '<div style="font-size:10px; color:#6f849c;">{{ cfgSource }}</div>'),
    ("kill switch metni sabit dosya yolu yazıyordu; hedef ortam adlandırılır (F01)",
     '<div style="font-size:12px; color:#dbe7f3; line-height:1.6;">Kalıcı bayrak <code>data/state/kill_switch.json</code> yazılır, restart\'ı hayatta kalır. K1 her girişi reddeder; açık pozisyonlar <b>FROZEN</b>, borsa SL/TP devrede. Çıkışlar serbest kalır. Sıfırlama yalnızca <code>make kill-reset REASON=…</code>.</div>',
     '<div style="font-size:12px; color:#dbe7f3; line-height:1.6;">Hedef ortam: <b style="{{ killEnvStyle }}">{{ killEnvLabel }}</b>. Kalıcı bayrak <code>{{ killPath }}</code> yazılır, restart\'ı hayatta kalır. K1 her girişi reddeder; açık pozisyonlar <b>FROZEN</b>, borsa SL/TP devrede. Çıkışlar serbest kalır. Sıfırlama elle yapılır.</div>'),
    ("modal erişilebilirliği: rol, etiket, Escape (F13)",
     '<div onClick="{{ stop }}" style="width:min(460px,92vw); border:1px solid #ff5470;',
     '<div onClick="{{ stop }}" role="dialog" aria-modal="true" aria-label="Kill switch onayı" style="width:min(460px,92vw); border:1px solid #ff5470;'),
    ("onay düğmesi istek sırasında kilitlenir (F12)",
     '<button onClick="{{ confirmKill }}" style="background:#ff5470; border:0; color:#070b12; font-weight:700; padding:8px 14px; cursor:pointer;">make kill</button>',
     '<button onClick="{{ confirmKill }}" style="{{ confirmKillBtn }}">{{ confirmKillLabel }}</button>'),
]


def template(design: str) -> str:
    """Tasarımın <x-dc>…</x-dc> bloğu, gerekçeli yerine koymalarla."""
    start, end = design.index("<x-dc>"), design.index("</x-dc>") + len("</x-dc>")
    body = design[start:end]
    for why, old, new in OVERRIDES:
        if body.count(old) != 1:
            raise SystemExit(f"yapı durdu: '{why}' için desen {body.count(old)} kez bulundu (1 bekleniyor)")
        body = body.replace(old, new)
    screen = (UI / "history-screen.html").read_text()
    if body.count("    </main>") != 1:
        raise SystemExit("yapı durdu: </main> tek değil; geçmiş ekranı yerleştirilemedi")
    return body.replace("    </main>", screen + "    </main>")


def strip_doc(html: str) -> str:
    return html.replace("</body>", "").replace("</html>", "").rstrip() + "\n"


def build() -> str:
    design = DESIGN.read_text()
    return (HEAD + template(design) + "\n"
            + strip_doc((UI / "console-logic.html").read_text())
            + strip_doc((UI / "keys-panel.html").read_text())
            + "\n</body>\n</html>\n")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="yalnızca doğrula, yazma")
    a = ap.parse_args(argv)
    out = build()
    target = UI / "index.html"
    if a.check:
        same = target.exists() and target.read_text() == out
        print("güncel" if same else "FARKLI — `make ui-build` çalıştır")
        return 0 if same else 1
    target.write_text(out)
    print(f"yazıldı: {target} ({len(out)} bayt)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
