# 🔢 Dasar Setiap Angka di SIAGA NUSA

Setiap ambang, bobot, dan batas di SIAGA NUSA dicatat di sini beserta asal dan alasannya. Asalnya dibagi tiga, dan ketiganya sengaja dibedakan:

| Label | Arti |
|---|---|
| 🟢 **Resmi BMKG** | Angka diambil dari dokumen atau praktik BMKG |
| 📊 **Dari data** | Angka dihitung atau dipilih dengan data, dan buktinya ada di notebook |
| ✋ **Pilihan tim** | Angka ditetapkan dengan alasan, tetapi tidak diturunkan dari data. Ditulis terbuka supaya bisa dikritik |

Per 23 November 2026. Kalau mengubah angka di kode, perbarui juga baris di sini.

---

## 1. Kategori hujan harian (dasar label dan skala di dasbor)

| Kategori | Hujan per hari | Asal |
|---|---|---|
| Tidak hujan | < 0,5 mm | 🟢 Resmi BMKG |
| Ringan | 0,5–20 mm | 🟢 Resmi BMKG |
| **Sedang** | **20–50 mm** | 🟢 Resmi BMKG |
| Lebat | 50–100 mm | 🟢 Resmi BMKG |
| Sangat lebat | 100–150 mm | 🟢 Resmi BMKG |
| Ekstrem | > 150 mm | 🟢 Resmi BMKG |

**Sumber:** tabel *Intensitas Hujan, CH perhari* pada [Surat Peringatan Dini Cuaca & Iklim BMKG, 10 Juli 2026](https://staklim-kalsel.bmkg.go.id/wp-content/uploads/2026/07/Kalsel-Dasarian-II-Juli-2026-TTE_signed.pdf). Rinciannya ada di [notebook 02](../notebooks/02_label_model_a.ipynb).

Hal yang perlu dibedakan saat menjelaskan:

- Perka BMKG KEP.009/2010 mendefinisikan *hujan lebat* sebagai ≥ 50 mm/24 jam, tetapi peraturan itu **sudah dicabut** oleh Peraturan BMKG No. 9/2022.
- Peraturan 2022 mengatur tingkatan peringatan (waspada/siaga/awas) **tanpa angka mm**.
- Jadi yang resmi adalah **batas-batas kategorinya**. BMKG tidak menetapkan "≥ 20 mm" sebagai ambang peringatan.

Kode: [`pipeline/rainfall.py`](../pipeline/rainfall.py), fungsi SQL `bmkg_category()` di [`sql/views.sql`](../sql/views.sql).

---

## 2. Model A: peluang hujan sedang ke atas besok

### Target ≥ 20 mm

| | |
|---|---|
| Nilai | Hujan harian ERA5 (00–24 WIB) **≥ 20 mm** |
| Asal | 🟢 Angkanya batas bawah kategori *sedang* BMKG. ✋ Memakainya sebagai target adalah pilihan tim |
| Alasan | ERA5 adalah rata-rata area ±25 km dan meratakan hujan deras lokal. Dari 28.728 kota-hari (2017–Okt 2026), hari **≥ 50 mm hanya 180 (0,63%)**; Jakarta hanya 7 hari dalam ±10 tahun, terlalu sedikit untuk dilatih. Hari **≥ 20 mm ada 2.171 (7,6%)**, cukup untuk dilatih |
| Konsekuensi | Di UI tertulis "hujan **sedang–lebat** (≥ 20 mm)", bukan "hujan lebat". Hari ≥ 50 mm tetap dipakai sebagai evaluasi tambahan |
| Bukti | [Notebook 02](../notebooks/02_label_model_a.ipynb) |

### Fitur prakiraan: Previous Runs, bukan Historical Forecast

| | |
|---|---|
| Nilai | Prakiraan yang terbit **sehari sebelumnya** (`*_previous_day1`), dari 4 model cuaca |
| Asal | 📊 Dari data |
| Alasan | Nilai Historical Forecast untuk hari H **identik** dengan run hari H sendiri: korelasi **1,000**, selisih **0,00 mm**. Pengecekan dilakukan di Jakarta, 90 hari (Des 2025–Feb 2026). Dipakai sebagai "prakiraan besok", arsip itu akan membocorkan jawaban. Prakiraan sehari sebelumnya hanya berkorelasi 0,579 dengan run hari H, dan inilah kondisi yang dihadapi model di dunia nyata |
| Konsekuensi | Arsip ini baru ada sejak **Februari 2024** (Januari 2024 masih kosong), jadi data latih hanya ±2,8 tahun. Rencana awal 2017–2026 tidak bisa dipakai |
| Bukti | [Notebook 04](../notebooks/04_model_a_hujan.ipynb), bagian awal; [`pipeline/ingest/previous_runs.py`](../pipeline/ingest/previous_runs.py) |

### Pembagian data berdasarkan waktu

| Bagian | Rentang | Kota-hari | Hari ≥ 20 mm |
|---|---|---:|---:|
| Latih | 9 Feb 2024 – 30 Jun 2025 | 4.064 | 350 (8,6%) |
| Validasi | 1 Jul – 31 Des 2025 | 1.472 | 121 (8,2%) |
| Uji | 1 Jan – 17 Nov 2026 | 2.568 | 126 (4,9%) |

- **Asal:** ✋ Pilihan tim.
- **Alasan:** dibagi menurut waktu, bukan acak, supaya model tidak belajar dari masa depan. Data latih memuat satu musim hujan penuh (2024/25). Data uji hanya dibuka sekali di akhir.
- Mulai 9 Feb, bukan 1 Feb, karena 8 hari pertama dipakai untuk menghitung hujan 7 hari terakhir.

### Pemilihan model

| Model | PR-AUC validasi |
|---|---:|
| **Regresi logistik, C = 0,1** | **0,327** |
| Regresi logistik, C = 1 | 0,325 |
| Random forest, kedalaman 6 | 0,296 |
| *Pembanding: prakiraan best_match (mm)* | *0,295* |
| XGBoost, kedalaman 5 | 0,291 |
| XGBoost, kedalaman 3 | 0,275 |
| Random forest, kedalaman 12 | 0,274 |

- **Asal:** 📊 Dari data. Model dengan PR-AUC validasi tertinggi yang dipilih.
- **Alasan model sederhana menang:** data ±2,8 tahun terlalu sedikit untuk model pohon, yang cenderung menghafal data latih.
- **Kenapa PR-AUC:** hari ≥ 20 mm hanya 5–9% dari semua hari. Akurasi akan tinggi walau model selalu menjawab "tidak", sedangkan PR-AUC menilai seberapa baik model menemukan hari yang jarang itu.

### Hasil di data uji 2026

| | Aturan "prakiraan ≥ 20 mm" | Model A |
|---|:-:|:-:|
| PR-AUC | 0,323 | **0,404** |
| F1 | 0,327 | **0,391** |
| Recall (hari ≥ 20 mm yang tertangkap) | 35% | **75%** |
| Presisi (peringatan yang terjadi) | **31%** | 26% |
| Hari ≥ 50 mm yang tertangkap | 2 dari 7 | **5 dari 7** |

Bootstrap per tanggal (2.000 kali) memberi selisih PR-AUC **+0,078**, dengan IK 95% [+0,013; +0,141]. Model A lebih baik di 99% sampel. Karena peluangnya terkalibrasi, angka "27%" berarti kejadian serupa memang terjadi sekitar 27% kali.

### Ambang kelas peluang

| Kelas | Peluang | Asal | Terjadi ≥ 20 mm (uji 2026) | (validasi 2025) |
|---|---|---|---:|---:|
| Rendah | < 13% | | 1,4%, ±1 dari 70 hari | 3,6% |
| Sedang | 13–35% | | 22%, ±1 dari 5 hari | 23% |
| Tinggi | ≥ 35% | | 45%, ±1 dari 2 hari | 45% |

- **13%** 📊 **Dari data:** ambang yang memaksimalkan F1 di data validasi (0,130).
- **35%** ✋ **Pilihan tim:** di ambang ini kelas Tinggi berisi hari yang kira-kira separuhnya benar-benar terjadi, dan pola itu konsisten di validasi maupun uji. Alternatifnya:

| Ambang Tinggi | Hari berkelas Tinggi (uji) | Yang terjadi |
|---|---:|---:|
| 30% | 83 | 43% |
| **35%** | **62** | **45%** |
| 40% | 44 | 55% |

**Kenapa 35% disebut tinggi:** hujan ≥ 20 mm biasanya hanya terjadi pada 5–9% hari, jadi 35% berarti 4–7 kali lebih besar dari hari biasa. Model juga jarang memberi peluang besar: hanya 1% hari yang mendapat > 51%. Kalau ambang Tinggi dipasang di 50%, kelas itu hampir tidak pernah muncul.

Kode: `PROB_LEVELS` di [`pipeline/model_a.py`](../pipeline/model_a.py).

### Angka lain di Model A

| Angka | Asal | Alasan |
|---|---|---|
| 4 model cuaca (best_match, ECMWF, GFS, ICON) | ✋ Pilihan tim | Model global utama yang punya arsip `previous_day1` untuk Indonesia. ECMWF ternyata fitur terpenting (korelasi peringkat dengan ERA5 0,79 vs best_match 0,70) |
| Hujan 1, 3, 7 hari terakhir | ✋ Pilihan tim | Mewakili tanah dan udara yang sudah basah. Hanya hari yang sudah lewat yang dipakai |
| Jumlah hujan harian hanya dari 24 jam lengkap | ✋ Pilihan tim | Jumlah dari sebagian jam akan terlihat seperti hari kering |
| Kalibrasi sigmoid di data validasi | 📊 Dari data | Bobot kelas membuat peluang mentah terlalu tinggi. Setelah kalibrasi, titik di grafik kalibrasi berimpit dengan diagonal |
| Prediksi langsung memakai run **terbaru** untuk besok | 📊 Dari data | Untuk tanggal yang belum terjadi, `previous_day1` berisi run kemarin, lebih basi daripada saat pelatihan |

---

## 3. Indeks risiko banjir (0–100)

### Bobot komponen

| Komponen | Bobot | Asal |
|---|:-:|---|
| Hujan 72 jam terakhir | 30 | ✋ Pilihan tim (plan §6.3), 📊 diuji data |
| Prakiraan 24 jam | 25 | ✋ Pilihan tim, 📊 diuji data |
| Debit sungai | 25 | ✋ Pilihan tim, 📊 diuji data |
| Riwayat laporan banjir | 20 | ✋ Pilihan tim |

**Alasan bobot awal:** hujan yang sudah turun paling langsung menyebabkan banjir, sedangkan riwayat banjir hanya latar belakang.

**Uji data** ([notebook 03](../notebooks/03_bobot_indeks_risiko.ipynb), Jakarta, 8 musim hujan 2017/18–2024/25):

- Dari 231 kombinasi bobot, AUC berkisar 0,54–0,68. Bobot manual (0,661) berada di median, hanya 0,023 di bawah kombinasi terbaik.
- Bobot hasil regresi logistik, divalidasi per musim, **tidak lebih baik** (0,662 vs 0,661 untuk banjir sedang; 0,757 vs 0,777 untuk banjir besar). Bobotnya juga tidak stabil antar musim.
- **Kesimpulan:** bobot manual dipertahankan. Batas ketajaman indeks ada di inputnya (ERA5 ±25 km), bukan di bobotnya.

Bobot riwayat banjir tidak bisa diuji, karena nilainya konstan untuk satu kota.

### Level Rendah / Sedang / Tinggi

| Level | Skor | Asal | Hari dengan ≥ 20 laporan banjir Jabodetabek (backtest Jakarta) |
|---|---|---|---:|
| Rendah | < 40 | ✋ Pilihan tim (plan §6.3) | 1,7% |
| Sedang | 40–69 | ✋ Pilihan tim | 4,8% |
| Tinggi | ≥ 70 | ✋ Pilihan tim | 9,8% |

Untuk banjir besar (≥ 50 laporan/hari): Rendah 0,2% → Sedang 1,6% → Tinggi 7,3%. Peluangnya naik berurutan, jadi pembagian level ini bermakna, meski angkanya sendiri dipilih tim.

Nama level sengaja tidak memakai *Waspada/Siaga/Awas*, karena istilah itu milik BMKG dan BPBD.

### Angka di dalam komponen

| Angka | Asal | Alasan |
|---|---|---|
| Hujan dan debit dibandingkan dengan **bulan yang sama** | ✋ Pilihan tim | 40 mm di Januari dan di Agustus tidak setara |
| Hanya bagian **di atas median** yang menambah poin | 📊 Dari data | Tanpa ini, hari biasa (persentil ±50) sudah mendapat setengah skor, dan hampir semua hari jatuh di Sedang |
| Skor prakiraan: ringan 0 · sedang 0,3 · lebat 0,6 · sangat lebat 0,85 · ekstrem 1 | ✋ Pilihan tim (plan §6.3), berdasarkan 🟢 kategori BMKG | Naik mengikuti kategori resmi. Hujan ringan tidak menambah risiko |
| Riwayat banjir: radius **5 km** | ✋ Pilihan tim | Kira-kira sama dengan satu sel grid 0,05° yang dipakai di seluruh sistem |
| Riwayat banjir: **proporsi hari** musim hujan, bukan proporsi musim | 📊 Dari data | Proporsi musim mentok di 8/8 untuk Jakarta (1.520 laporan) maupun Bogor (18 laporan). Proporsi hari membedakannya: 25% vs 1% |
| Riwayat banjir: skor penuh di **20%** hari | ✋ Pilihan tim | Skor penuh kalau 1 dari 5 hari musim hujan ada laporan. Jakarta (25%) mencapainya |
| Musim hujan = **November–April** | ✋ Pilihan tim | Pola umum musim hujan di Jawa |
| Riwayat debit GloFAS mulai **2010** | ✋ Pilihan tim | 16 tahun cukup untuk persentil per bulan (±480 hari per bulan) |
| Hujan 72 jam dianggap ada kalau **≥ 60 jam** tercakup | ✋ Pilihan tim | Snapshot prakiraan kadang bolong. Kalau lebih dari 12 jam hilang, komponen ini dianggap tidak tersedia daripada menghitung dari data sepotong |
| Komponen tanpa data → bobotnya dibagi ke komponen lain | ✋ Pilihan tim | Kota di luar Jabodetabek tidak punya laporan warga. Ini lebih jujur daripada memberi nilai nol |

Kode: [`pipeline/risk.py`](../pipeline/risk.py).

---

## 4. Sungai (GloFAS)

| Angka | Asal | Alasan |
|---|---|---|
| Satu sel sungai per kota, dipilih manual | 📊 Dari data | Grid GloFAS 0,05° (±5,5 km) tidak selalu menaruh sungai kecil di sel terdekat. Sel dipilih dari grid 7×7 debit, mengikuti alur yang debitnya naik ke hilir |
| Uji pilihan sel | 📊 Dari data | Korelasi peringkat debit dengan hujan 3 hari ERA5 kotanya **0,71–0,87** untuk semua kota |
| Hari GloFAS dalam **UTC** | 📊 Dari data | Parameter zona waktu menggeser nilai satu hari, karena GloFAS menghitung rata-rata per hari UTC |

Kode: [`pipeline/rivers.py`](../pipeline/rivers.py).

---

## 5. Pembersihan laporan banjir warga (PetaBencana)

| Angka | Asal | Alasan |
|---|---|---|
| Ledakan laporan: **≥ 10 laporan** per sel-jam dengan foto **< 50%**, atau **≥ 25 laporan** | 📊 Dari data | Banjir besar sungguhan (1 Jan 2020, 25 Feb 2020, 20 Feb 2021) paling banyak ±18 laporan per sel-jam. Kumpulan di atas itu dengan sedikit foto adalah sesi latihan |
| Kata kunci latihan/uji (HKB, simulasi, latihan, *drill*, tes, …) dan kode mitra `tescode` | 📊 Dari data | ±53% laporan banjir Jabodetabek di arsip ternyata latihan atau uji, walau berstatus `confirmed` |
| Kedalaman sah **0–500 cm** | ✋ Pilihan tim | Nilai di luar rentang itu dianggap salah ketik dan dikosongkan, bukan dibuang seluruh laporannya |

Kode: [`pipeline/clean/petabencana.py`](../pipeline/clean/petabencana.py), [`pipeline/transform/floods.py`](../pipeline/transform/floods.py).

---

## 6. Tampilan

| Angka | Asal | Alasan |
|---|---|---|
| Hujan "mulai" = jam pertama **≥ 0,5 mm/jam** | ✋ Pilihan tim | Mengikuti batas "tidak hujan" BMKG (0,5 mm), tetapi diterapkan per jam |
| Jendela prakiraan **24 jam** dari jam sekarang | ✋ Pilihan tim | Kategori BMKG berlaku untuk jumlah per 24 jam |
| Badge BMKG/Open-Meteo kuning kalau data **> 6 jam** atau ada kota yang gagal | ✋ Pilihan tim | Snapshot dijadwalkan tiap jam, tetapi GitHub Actions hanya menjalankannya ±3 kali sehari |
| Badge PetaBencana kuning kalau laporan terakhir **> 72 jam** | ✋ Pilihan tim | Di musim kemarau, tidak ada laporan berhari-hari itu wajar. Badge kuning hanya menandai bahwa datanya lama, bukan rusak |
| Satu "run" BMKG = snapshot dalam **10 menit** | 📊 Dari data | BMKG diambil per kota dengan jeda 1 detik, jadi satu run tersebar beberapa detik |

---

## 7. Pertanyaan juri yang mungkin muncul

**"Kenapa 20 mm, bukan 50 mm yang disebut hujan lebat?"**
Angka 20 mm adalah batas resmi kategori *sedang* BMKG. Hujan ≥ 50 mm di data ERA5 hanya 0,63% hari, terlalu sedikit untuk dilatih, karena ERA5 merata-ratakan area ±25 km. Hari ≥ 50 mm tetap dinilai: Model A menangkap 5 dari 7, sedangkan aturan biasa hanya 2.

**"Peluang 35% kok disebut tinggi?"**
Hujan ≥ 20 mm biasanya hanya terjadi pada 1 dari 12–20 hari. Di data uji, hari dengan peluang ≥ 35% benar-benar hujan ≥ 20 mm separuh dari waktunya, 30 kali lebih sering daripada kelas Rendah.

**"Kenapa datanya cuma sejak 2024?"**
Arsip prakiraan yang terbit sehari sebelumnya baru ada sejak Februari 2024. Arsip yang lebih panjang (sejak 2017) ternyata berisi prakiraan hari H sendiri, jadi akan membocorkan jawaban. Kami memilih data yang lebih pendek tapi jujur.

**"Kenapa regresi logistik, bukan XGBoost?"**
Tiga jenis model (regresi logistik, random forest, XGBoost, masing-masing dua pengaturan) diuji di data validasi. Regresi logistik menang: PR-AUC 0,327, sedangkan XGBoost terbaik 0,291. Dengan data ±2,8 tahun, model yang lebih rumit cenderung menghafal.

**"Bobot indeks risiko dari mana?"**
Ditetapkan manual, lalu diuji: 231 kombinasi lain dan bobot hasil belajar mesin tidak memberi hasil yang lebih baik. Bukti ada di notebook 03.

**"Apakah ini sistem peringatan dini?"**
Bukan. Level Rendah/Sedang/Tinggi sengaja tidak memakai istilah *Waspada/Siaga/Awas*. Peringatan resmi tetap dari BMKG dan BPBD.
