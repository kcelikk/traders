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
