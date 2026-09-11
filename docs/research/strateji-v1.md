# Strateji v1 — ön kayıtlı hipotez dokümanı

Durum: **H5 reddedildi** (ölçüm aşağıda) · Tarih: 2026-09-11 · Yöntem: ADR 0008, ADR 0010

Bu doküman `config/*.toml` içindeki `[decision].allowed_cells`, `sl_pct` ve `tp_pct` alanlarının
neye dayanarak doldurulduğunu kayda geçirir. Doldurmadan **önce** yazılır; sayılar sonradan
eklenir. Amaç, seçimin veriye bakıp sonuç aramakla değil, önceden tanımlı bir kuralla yapıldığını
gösterebilmektir.

## Bağlam: elimizde ne var

Faz 3 (30 gün, 460.341 bar, 10 sembol, sabit ufuklar) **48 hücrenin hiçbirinde** maliyet üstü
beklenti bulamadı. En iyi hücreler 60 dakikalık long hücreleriydi ve bu, dönemin yukarı
sürüklenmesidir: tüm long'lar pozitif, tüm short'lar negatifti; durum etiketinden bağımsız.

| Doğrulama, taker/taker | brüt % | maliyet % | net % | CI |
|---|---|---|---|---|
| S4 long 60 dk | 0,110 | 0,101 | **0,009** | −0,081 … 0,097 |
| S1 long 60 dk | 0,101 | 0,100 | **0,000** | −0,060 … 0,060 |
| S3 long 60 dk | 0,090 | 0,101 | −0,011 | −0,081 … 0,059 |

Hepsinin güven aralığı sıfırı içeriyor. Bu tablodan bir hücre seçmek, ölçümün desteklemediği
bir iddiayı koda gömmek olur.

## Faz 3'te denenmemiş olan: çıkış mekaniği

Faz 3 sabit ufuklu çıkış ölçtü: "15 dakika sonra kapat". Gerçek sistem sabit ufukla çıkmıyor;
girişte borsaya stop ve hedef koyup hangisi önce gelirse onu alıyor. Aynı giriş sinyali, farklı
çıkış mekaniğiyle farklı beklenti üretebilir. Bu, veriye yeni bir soru sormaktır, aynı soruyu
tekrar sormak değil.

**Hipotez H5:** Bir (durum, yön) hücresi için, girişte konan stop/hedef çiftiyle yönetilen
pozisyonun maliyet düşülmüş net beklentisi, aynı hücrenin sabit ufuklu beklentisinden farklıdır
ve en az bir birleşimde sıfırın anlamlı ölçüde üstündedir.

**Karar kuralı (önceden sabit):** Bir (durum, yön, stop, hedef, süre) birleşimi ancak hem keşif
(ilk %70) hem doğrulama (son %30) diliminde bootstrap güven aralığının **alt sınırı sıfırın
üstündeyse** `allowed_cells`'e girer. Tek dilimde geçmek yetmez. Eşik sonradan gevşetilmez.

**Ölçüm aracı:** `scripts/barrier_scan.py` (üçlü bariyer: stop, hedef, süre). Aynı barda iki
bariyere de dokunulduğunda **stop önce** varsayılır; bu varsayım sonucu karamsar yönde yanlı yapar.

## Sonuç: H5 reddedildi

Tarama: `scripts/barrier_scan.py`, 460.341 bar, 10 sembol, 2026-08-09 – 2026-09-09.
Izgara: 4 durum × 2 yön × 2 tutma süresi (15/60 dk) × 4 stop (0,3–1,2 %) × 5 hedef (0,3–2,4 %)
= **320 birleşim**, her iki maliyet senaryosunda ayrı ayrı.

| Senaryo | Değerlendirilen | Karar kuralını geçen |
|---|---|---|
| taker/taker (maliyet ≈ 0,10 %) | 320 | **0** |
| maker/taker (maliyet ≈ 0,07 %) | 320 | **0** |

En iyi beş birleşim, doğrulama dilimi, taker/taker:

| Hücre | tut | stop % | hedef % | n | net % | CI |
|---|---|---|---|---|---|---|
| S1 long | 60 | 1,20 | 2,40 | 4.864 | −0,075 | −0,098 … −0,052 |
| S4 long | 60 | 1,20 | 2,40 | 4.338 | −0,080 | −0,107 … −0,054 |
| S1 long | 60 | 1,20 | 1,60 | 4.864 | −0,081 | −0,103 … −0,060 |
| S3 long | 60 | 0,80 | 2,40 | 10.762 | −0,084 | −0,097 … −0,071 |
| S3 long | 60 | 0,50 | 2,40 | 10.762 | −0,084 | −0,095 … −0,073 |

Bu, Faz 3'ün sonucundan **daha güçlü** bir redde işaret ediyor. Faz 3'te en iyi hücrelerin güven
aralığı sıfırı içeriyordu, yani "belirsiz"di. Bariyerli çıkışta en iyi birleşimlerin bile güven
aralığı **tamamen sıfırın altında**: bu hücreler belirsiz değil, ölçülebilir biçimde zarar
ediyor. Kayıp büyüklüğü işlem başına yaklaşık maliyet kadar (0,08–0,09 %), yani brüt beklenti
hâlâ sıfır civarında ve maliyet net sonucu belirliyor.

Maker girişi (maliyet 0,10 → 0,07 %) sonucu değiştirmiyor: en iyi birleşim −0,045 %, güven
aralığı yine tamamen negatif.

**Karar: `allowed_cells` yön tahmini amacıyla doldurulmaz.** Bu tablodan bir satır seçip config'e
yazmak, ölçümün zarar ettiğini gösterdiği bir kuralı koda gömmek olurdu.

### Çıkış karışımı (tesisat testi için gerekli bilgi)

S1→long, S2→short girişlerinde hangi çıkışın ne sıklıkta tetiklendiği:

| stop/hedef/tutma | n | hedef % | stop % | süre % | ort. bar | net % |
|---|---|---|---|---|---|---|
| 0,5 / 1,0 / 60 | 93.035 | 11,8 | 32,7 | 55,4 | 44,2 | −0,119 |
| **0,5 / 0,6 / 60** | 93.035 | **24,1** | **30,2** | **45,7** | 39,9 | −0,116 |
| 0,3 / 0,6 / 15 | 93.035 | 9,2 | 25,9 | 64,9 | 12,2 | −0,116 |
| 0,8 / 1,6 / 60 | 93.035 | 5,8 | 19,3 | 74,9 | 52,1 | −0,122 |

Kalın satır üç çıkış yolunu da en dengeli çalıştıran ayardır. Kâr beklentisi taşımaz; yalnızca
emir yolunun her dalını test etmeye elverişlidir.

## H5 reddedilirse ne olur

`allowed_cells` boş kalır ve yön tahminine dayalı giriş yazılmaz. Faz 9'un hedefi zaten kârlılık
değil tesisat doğrulamasıdır (ADR 0015): emir yolu, koruma emirleri, mutabakat ve R1–R5'in
gerçek borsada çalıştığı, kâr iddiası olmayan bir giriş kuralıyla da doğrulanabilir. Bu durumda
iki ayrı şey birbirinden ayrılır:

- **Tesisat testi (testnet):** kâr beklentisi olmayan, açıkça öyle etiketlenmiş bir giriş kuralı.
- **Strateji arayışı (araştırma):** Faz 3 karar dokümanındaki B yolu — bu fazda hiç kullanılmamış
  veri (`forceOrder` likidasyon kaskadları, `depth` dengesizliği, funding uçları) üzerine yeni
  hipotez döngüsü.

Bu ikisi karıştırılmaz. Testnet'te işlem açılıyor olması stratejinin çalıştığı anlamına gelmez.


---

## İkinci tur: çoklu zaman dilimi ve kullanılmayan veri (2026-09-11)

Proje sahibinin tespiti üzerine iki eksik kapatıldı ve aynı karar kuralıyla yeniden ölçüldü.

### Ne değişti

1. **Zaman dilimi.** Sistem yalnızca 1 dakikalık bar üretiyordu. Artık 1 dk barlardan 3/5/15/30/60
   dakikalık barlar türetiliyor (epoch'a hizalı, tamamlanmamış kova düşürülür).
2. **Kullanılmayan veri.** Defter derinliği (`bookDepth`) ve konumlanma metrikleri (`metrics`)
   arşivden indirildi ve barlara eklendi: 460.341 barın tamamı iki kaynağı da aldı.
3. **Funding maliyeti.** Bariyer hesabı funding'i hiç saymıyordu. 30 saatlik bir tutmada üç ödeme
   kaçıyordu ve uzun zaman dilimleri olduğundan iyi görünüyordu. Artık sayılıyor.

### H5 tekrar: durum etiketleri, tüm zaman dilimleri

| Zaman dilimi | Bar | Birleşim | Geçen | En iyi doğrulama net % |
|---|---|---|---|---|
| 1 dk | 460.341 | 360 | 0 | −0,078 |
| 3 dk | 153.163 | 360 | 0 | +0,071 |
| 5 dk | 91.740 | 360 | 0 | +0,091 |
| 15 dk | 30.357 | 360 | 0 | +0,305 |
| 30 dk | 15.046 | 280 | 0 | +0,470 |
| 60 dk | 7.434 | 40 | 0 | örneklem yetersiz |

Doğrulama netleri zaman dilimiyle birlikte yükseliyor ama **hiçbiri geçmiyor**, çünkü keşif dilimi
aynı yönde davranmıyor. En iyi satır (30 dk, S3 long, stop 1,20 %, hedef 2,40 %): keşif +0,019 %,
doğrulama +0,470 %. İki yarının bu kadar ayrışması sinyal değil gürültü işaretidir; karar kuralı
tam bunun için önceden yazılmıştı. Ayrıca örneklem çöküyor: 30 dakikada doğrulama dilimi 130 işlem.

### H6–H8: kullanılmayan veriden üretilen sinyaller

| Hipotez | Giriş kuralı | Birleşim | Geçen | En iyi doğrulama net % |
|---|---|---|---|---|
| H6 defter dengesizliği | ±%1 bandında alış/satış notional ucu | 320 | 0 | +0,024 (5 dk, long) |
| H7 açık pozisyon değişimi | OI artışı ucunda fiyat yönüne uy | 280 | 0 | +0,020 (30 dk, long) |
| H8 taker oranı tükenmesi | aşırı alış baskısında ters yön | 320 | 0 | −0,015 (30 dk, long) |

**Üçü de reddedildi.** En iyi satırların güven aralıkları sıfırı içeriyor.

### Ortaya çıkan tek tutarlı örüntü

Her üç sinyalde ve her zaman diliminde aynı şey görülüyor: **short yönü net biçimde zarar ediyor,
long yönü sıfır civarında.**

| Sinyal | En iyi long | En iyi short |
|---|---|---|
| defter dengesizliği | +0,024 (CI −0,042 … +0,089) | −0,047 (CI −0,087 … −0,008) |
| OI değişimi | +0,020 (CI −0,180 … +0,243) | −0,127 (CI −0,131 … −0,123) |
| taker oranı | −0,015 (CI −0,148 … +0,136) | −0,090 (CI −0,137 … −0,046) |

Bu, sinyalin bilgisi değil dönemin yukarı sürüklenmesidir. Sinyali tersine çevirsek de aynı
tablo çıkardı. Yani bu üç kaynak da, en azından bu kurgu ve bu dönemde, yön bilgisi taşımıyor.

### Sınırlar

- 32 gün, tek rejim. Düşüş rejiminde tablo simetrik biçimde ters dönerdi; bu, long tarafın
  gerçekten kazandığı anlamına gelmez.
- Yüksek zaman dilimlerinde örneklem küçük: 30 dakikada doğrulama 130–280 işlem.
- Defter dengesizliği dakikada bir örnekle ölçülüyor (arşiv çözünürlüğü), sürekli değil.
- Konumlanma metrikleri 15 dakikada bir yayınlanıyor; 1 ve 5 dakikalık dilimlerde aynı değer
  tekrar ediliyor, bu da o dilimlerde sinyali zayıflatıyor.


---

## Üçüncü tur: likidasyon kaskadları (2026-09-11)

### Veri

Likidasyon verisi Binance arşivinde **yok**. S3 dizin listesiyle doğrulandı: `aggTrades`,
`bookDepth`, `bookTicker`, `indexPriceKlines`, `klines`, `markPriceKlines`, `metrics`,
`premiumIndexKlines`, `trades`. Likidasyon yalnızca canlı `forceOrder` akışında var, yani
yalnızca kendi kaydımızda.

`scripts/extract_liquidations.py` 234.937.455 satır tarayıp 13.222 likidasyon olayı çıkardı;
4.721 dakikada en az bir olay var. Kapsam: 36 saat, 10 sembol.

### Hipotezler (ölçümden önce yazıldı)

- **H9 tükenme:** yoğun long likidasyonu (zorunlu satış) dip işaretidir → long.
- **H10 devam:** kaskad fiyatı ittirir → likidasyon baskısının yönüne uyulur.

İkisi kasten birbirinin zıddı. Sinyal yalnızca toplam likidasyon hacmi üst bantta olan barlarda
üretilir; yön net baskının işaretinden gelir.

### Ön bakış yanıltıcı çıktı

Üç saatlik ham örnekte tablo umut vericiydi: long likidasyonu baskın dakikalardan sonra fiyat
15 dakikada ortalama **+0,32 %**, short likidasyonu baskın dakikalardan sonra **−0,10 %**. Simetrik
ve maliyet üstü görünüyordu. **Tam ölçüm bunu doğrulamadı.**

### Sonuç: H9 ve H10 reddedildi

| Hipotez | Birleşim | Geçen | En iyi long | En iyi short |
|---|---|---|---|---|
| H9 tükenme | 80 | **0** | +0,304 (keşif −0,250) | −0,175 |
| H10 devam | 80 | **0** | +0,203 (keşif −0,148) | −0,130 |

İki bağımsız gerekçeyle reddedildi:

1. **Keşif ve doğrulama zıt işaretli.** En iyi satırda keşif −0,250 %, doğrulama +0,304 %. İki
   yarının işareti değişiyorsa elde sinyal değil gürültü vardır. 36 saatlik veride keşif ilk
   ~25 saat, doğrulama son ~11 saat; ikisinde piyasa yönü farklı.
2. **Zıt iki hipotez aynı anda "kazanıyor".** H9 ve H10 tanım gereği birbirinin tersidir; biri
   doğruysa diğeri kaybetmek zorundadır. İkisinin de doğrulamada pozitif long çıkması, kazandıran
   şeyin kaskad yönü değil **dönemin yukarı gidişi** olduğunu gösterir. Nitekim her iki hipotezde
   de short tarafı net zarar ediyor, ortalama doğrulama neti long +0,00/+0,04 %, short −0,27/−0,20 %.

Bu, önceki iki turda görülen örüntünün aynısıdır.

### Sınır: veri kısa

36 saat bir hipotezi doğrulamak için yeterli değil. 5 ve 15 dakikalık dilimler ısınma penceresini
dolduramadığı için hiç ölçülemedi. Likidasyon verisi arşivde olmadığından tek yol kaydın
birikmesini beklemek: **her gün +24 saat**. Bu hipotez, kayıt en az iki haftaya ulaştığında
tekrar test edilmeye değer; o zaman keşif/doğrulama ayrımı farklı rejimler içerebilir.
