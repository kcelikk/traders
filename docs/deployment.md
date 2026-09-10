# Dağıtım: nginx gateway ve konsol erişimi

Tarih: 2026-09-10. Sunucu tek makine, birden fazla proje barındıracak biçimde kuruldu.

## Akış

```
İnternet → Cloudflare (TLS sonlandırma, DNS: traders.btadmin.net)
        → sunucu :443  → nginx (vhost: traders.btadmin.net)
        → 127.0.0.1:8787 fbot konsolu (systemd: fbot-console)
```

Konsol **yalnızca 127.0.0.1** dinler; dışarıdan doğrudan erişilemez, tek kapı nginx'tir.

## Üç güvenlik katmanı

1. **HTTP Basic Auth** (nginx): `/etc/nginx/tls/traders.htpasswd`, kullanıcı `traders`.
   Parola değiştirme: `htpasswd /etc/nginx/tls/traders.htpasswd traders`
2. **Uygulama token'ı** (yazma uçları): `FBOT_UI_TOKEN`, `/opt/traders/.env.ui` içinde (izin 600, gitignore'da).
   Token yoksa `POST /api/kill` ve `/api/kill/reset` **tamamen kapalıdır** (fail-closed).
   Tarayıcı ilk yazma denemesinde token sorar ve `localStorage`'a saklar.
3. **Ağ** — konsol 127.0.0.1'e bağlı, nginx `client_max_body_size 1m`, `/api/` için 10 r/s (burst 20), kill uçları için burst 5.

Ek: bilinmeyen host adları `444` ile reddedilir (`000-default-deny`); Cloudflare IP aralıkları `set_real_ip_from` ile tanımlı, gerçek istemci IP'si `CF-Connecting-IP`'den okunur.

## Sertifika

Şu an **self-signed** (`/etc/nginx/tls/traders.crt`, 10 yıl). Cloudflare SSL modu **Full** ile çalışır.
Daha güvenli iki seçenek:

- **Cloudflare Origin CA** (önerilen): panelden sertifika üret, `traders.crt`/`traders.key` yerine koy, SSL modunu **Full (strict)** yap. Yenileme derdi yok (15 yıl).
- **Let's Encrypt**: 80 portu dışarıdan erişilebilir olmalı. `apt install certbot python3-certbot-nginx && certbot --nginx -d traders.btadmin.net`. ACME webroot hazır: `/var/www/acme`.

## Yeni proje ekleme

```bash
cp /etc/nginx/sites-available/traders.btadmin.net /etc/nginx/sites-available/<yeni-domain>
# server_name ve proxy_pass portunu değiştir, kendi htpasswd dosyasını ver
ln -s /etc/nginx/sites-available/<yeni-domain> /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```
Her proje kendi vhost'unu, kendi kimlik dosyasını ve kendi 127.0.0.1 portunu kullanır. Ortak parçalar:
`snippets/security-headers.conf`, `snippets/cloudflare-realip.conf`.

## Servisler

| Servis | Yönetim | Not |
|---|---|---|
| `fbot-console` | systemd, `Restart=always`, 1 GB / 1 CPU | konsol API + statik UI |
| `fbot-recorder` | docker compose | ham kayıt |
| `fbot-paper` | docker compose | paper trading, izole |
| `nginx` | systemd | gateway |

`systemctl status fbot-console` · `journalctl -u fbot-console -n 50` · log: `data/ui.log`

## Doğrulanan davranış (2026-09-10)

| Test | Sonuç |
|---|---|
| Kimliksiz istek | 401 |
| Basic auth ile sayfa | 200, 91 KB |
| HTTP → HTTPS | 301 |
| Bilinmeyen host | bağlantı kapatıldı (444) |
| `POST /api/kill` token'sız | `{"error":"token geçersiz"}` |
| `POST /api/kill` token ile | kill switch açıldı, `reset` ile kapatıldı |
| Konsol dış arayüze bağlı mı | hayır, yalnızca 127.0.0.1:8787 |

## Kalan

- Cloudflare tarafında SSL modunun **Full** (self-signed ile) ya da Origin CA sonrası **Full (strict)** olması gerekir.
- İsteğe bağlı sertleştirme: nginx'i yalnızca Cloudflare IP aralıklarından gelen bağlantılara açmak (`allow`/`deny`).
