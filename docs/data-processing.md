# 🔁 Perjalanan Data SIAGA NUSA

Dokumen ini menelusuri perjalanan satu angka, dari respons mentah API BMKG atau Open-Meteo sampai muncul di dasbor sebagai *"Jakarta diprakirakan hujan ringan mulai pukul 12.00"*. Semua angka di sini berasal dari eksekusi nyata pipeline pada **23 November 2026**.

**Prinsip yang dipegang di setiap tahap:**

1. **Data mentah tidak pernah diubah atau dibuang.** Pembersihan selalu dikerjakan pada salinannya.
2. **Nilai kosong dibiarkan kosong.** Angka hujan tidak pernah diisi tebakan, karena angka karangan di aplikasi cuaca dan banjir bisa menyesatkan orang.
3. **Baris yang ditolak disimpan beserta alasannya** di tabel karantina, tidak dihapus diam-diam.
4. **Setiap job aman dijalankan berulang (idempotent).** Menjalankan ulang tidak membuat baris ganda.
5. **Setiap angka membawa sumber dan waktunya** sampai ke layar.

---

## 🗺️ Gambaran besar

```mermaid
flowchart LR
    subgraph Sumber
        BMKG["BMKG<br/>prakiraan per 3 jam"]
        OM["Open-Meteo<br/>prakiraan per jam"]
        ERA["Open-Meteo Archive<br/>ERA5 harian"]
        PB["PetaBencana<br/>laporan banjir warga"]
    end

    GHA["GitHub Actions<br/>snapshot.yml"] -->|commit JSON| BR[("branch<br/>data-snapshots")]
    BMKG --> GHA
    OM --> GHA

    BR -->|sync| SNAP["data/snapshots/"]
    SNAP -->|raw · ELT| RAW[("raw_payloads<br/>jsonb")]
    SNAP -->|forecasts · ETL pandas| FC[("forecast_bmkg<br/>forecast_hourly")]
    ERA -->|history| OBS[("obs_daily")]
    PB -->|floods| FR[("flood_reports")]
    FC -. ditolak .-> Q[("quarantine")]

    RAW --> V["views.sql<br/>CTE · window · FILTER"]
    FC --> V
    OBS --> V
    FR --> V
    V --> API["FastAPI<br/>/api/*"]
    API --> WEB["Dasbor · Peta · Status"]
```

Pipeline dijalankan dengan satu perintah, `python -m pipeline.run all`, yang mengeksekusi job berurutan: `init → sync → raw → forecasts → history → floods → views`.

---

## 1. Sumber data

| Sumber | Isi | Frekuensi | Kenapa dipakai | Label di UI |
|---|---|---|---|---|
| **BMKG** `api.bmkg.go.id/publik/prakiraan-cuaca` | Prakiraan resmi per kelurahan, blok 3 jam, 3 hari ke depan | Terbit ±2× sehari | Satu-satunya sumber **resmi** | 🟢 Resmi |
| **Open-Meteo Forecast** | Prakiraan per jam, 7 hari: hujan, peluang hujan, suhu, kelembapan, angin, awan | Diperbarui per jam | Resolusi jam, dipakai untuk grafik dan peta | 🔵 Data model cuaca |
| **Open-Meteo Archive (ERA5)** | Hujan harian historis sejak 2017 | Harian, tertinggal ±5 hari | Akumulasi hujan dan label Model A | 🔵 Data model cuaca |
| **PetaBencana.id** | Laporan banjir warga (titik koordinat) | Realtime | Bukti kejadian banjir di lapangan | 🟡 Laporan warga |

Lokasi pilot ada 8 kota, dengan titik koordinat diambil dari kelurahan BMKG supaya BMKG dan Open-Meteo merujuk ke titik yang sama ([`pipeline/locations.py`](../pipeline/locations.py)). Makassar memakai **WITA**, kota lain WIB.

---

## 2. Extract: mengumpulkan data

### 2.1 Kenapa harus mengumpulkan sendiri

BMKG **tidak menyediakan arsip prakiraan**. Prakiraan yang terbit pagi ini akan hilang ketika prakiraan sore terbit. Padahal SIAGA NUSA perlu menjawab *"apa yang berubah sejak pembaruan sebelumnya?"*, dan nanti melatih model dari prakiraan masa lalu. Karena itu setiap respons disimpan sendiri.

### 2.2 Snapshot oleh GitHub Actions

Workflow [`snapshot.yml`](../.github/workflows/snapshot.yml) memanggil BMKG (8 kota, jeda 1 detik antar-kota) dan Open-Meteo (8 kota dalam satu panggilan), lalu meng-commit hasilnya ke branch terpisah `data-snapshots`. Setiap respons dibungkus dalam *envelope*:

```json
{
  "source": "bmkg",
  "location": "jakarta",
  "fetched_at": "2026-11-23T02:48:51Z",
  "request": {"url": "https://api.bmkg.go.id/publik/prakiraan-cuaca", "params": {"adm4": "31.71.03.1001"}},
  "status": 200,
  "error": null,
  "payload": { "...respons asli, tidak diubah..." }
}
```

- Tata letaknya `snapshots/<sumber>/<tanggal>/<jam>Z/<kota>.json` (UTC). File dibuka dengan mode `"x"`, jadi **tidak pernah bisa ditimpa**.
- Panggilan yang gagal tetap disimpan, lengkap dengan pesan error-nya. Kegagalan juga data: dari situ halaman Status tahu kapan sumber bermasalah.
- **Jadwal vs kenyataan.** Cron sudah diset tiap jam (menit ke-17) sejak 19 Nov, tetapi GitHub sering menunda atau melewati cron. Hasilnya hanya **±3 run per hari**, dengan jeda 5–9 jam. Total ada **51 run** antara 6 dan 23 Nov 2026.

### 2.3 Job `sync`

[`pipeline/sync.py`](../pipeline/sync.py) menjalankan `git fetch origin data-snapshots`, lalu `git archive` mengekstrak folder `snapshots/` ke `data/snapshots/`. Ekstraksi memakai `tarfile` dengan `filter="data"` supaya isi arsip tidak bisa menulis ke luar folder tujuan. Hasil hari ini: **816 file** (408 BMKG + 408 Open-Meteo).

### 2.4 Sumber yang ditarik langsung

| Job | Cara | Catatan |
|---|---|---|
| `history` (ERA5) | Backfill dari file arsip 2017–2026, lalu **menyusul hari yang belum ada** lewat API arsip Open-Meteo | ERA5 tertinggal ±5 hari, sehingga API mengembalikan `null` untuk hari terbaru. Hari itu **dibuang, bukan disimpan kosong**: kalau baris kosong sudah tersimpan, `ON CONFLICT DO NOTHING` akan menghalangi angka aslinya masuk nanti |
| `floods` (PetaBencana) | Arsip **bulan lalu dan bulan ini ditarik ulang** setiap eksekusi, lalu semua arsip lokal dimuat | Laporan yang datang terlambat ikut masuk |

---

## 3. Dua jalur: ELT dan ETL

Pola dari sesi 11 dipakai berdampingan, masing-masing untuk kebutuhan yang berbeda:

| | **ELT**: job `raw` | **ETL**: job `forecasts`, `history`, `floods` |
|---|---|---|
| Urutan | Extract → **Load** apa adanya → Transform di SQL | Extract → **Transform** di pandas → Load yang sudah bersih |
| Tujuan | Arsip lengkap yang bisa diperiksa ulang kapan saja, termasuk panggilan yang gagal | Tabel siap pakai untuk API dan model |
| Tabel | `raw_payloads` (kolom `payload` bertipe `jsonb`) | `forecast_bmkg`, `forecast_hourly`, `obs_daily`, `flood_reports` |
| Contoh pemakaian | View `v_source_freshness` menghitung kesegaran sumber langsung dari `raw_payloads` | Grafik hujan per jam, ranking wilayah |

Kalau aturan pembersihan diubah, tabel ETL bisa dibangun ulang dari `raw_payloads` atau `data/snapshots/` tanpa memanggil API lagi.

---

## 4. Transform: membersihkan dengan pandas

Kode: [`pipeline/transform/forecast.py`](../pipeline/transform/forecast.py) dan [`pipeline/transform/floods.py`](../pipeline/transform/floods.py). Langkahnya sama untuk tiap sumber.

### 4.1 Meratakan JSON bersarang

Respons BMKG bersarang empat tingkat: `payload → data[] → cuaca[hari][] → blok 3 jam`. Setiap blok dijadikan satu baris tabel:

```text
SEBELUM (JSON)                                   SESUDAH (DataFrame, satu baris per blok)
{"datetime": "2026-11-23T03:00:00Z",             location  analysis_at          valid_at             precip_mm  weather_desc
 "analysis_date": "2026-11-23T00:00:00",    →    jakarta   2026-11-23 00:00+00  2026-11-23 03:00+00  0.3        Berawan
 "tp": 0.3, "t": 31, "hu": 71,
 "weather_desc": "Berawan", ...}
```

Open-Meteo sebaliknya berbentuk **lebar**: satu array per variabel (`"precipitation": [0.0, 0.0, ...]`, 168 jam). Array itu diubah menjadi bentuk **panjang**, satu baris per (kota, run, jam). Nama kolom juga diseragamkan dengan satuannya, misalnya `relative_humidity_2m` menjadi `humidity_pct`.

### 4.2 Konversi tipe dan zona waktu

- Teks waktu diubah menjadi `datetime` UTC (`pd.to_datetime(..., utc=True)`). Semua waktu disimpan dalam UTC dan baru dikonversi ke WIB/WITA saat ditampilkan.
- `analysis_date` BMKG tidak membawa zona waktu. Nilainya jam run model (00 atau 12), jadi dibaca sebagai UTC.
- Angka diubah dengan `pd.to_numeric(errors="coerce")`. Teks yang tidak bisa dibaca menjadi `NaN`, tidak membuat job crash.
- Teks dirapikan: `" Berawan "` menjadi `"Berawan"`, arah angin `"n"` menjadi `"N"`.

### 4.3 Membuang duplikat

Satu terbitan BMKG bertahan ±12 jam, sehingga ikut terambil di beberapa snapshot. Baris diurutkan menurut `fetched_at`, lalu `drop_duplicates(["location", "analysis_at", "valid_at"], keep="first")`. Kolom `first_fetched_at` mencatat kapan terbitan itu pertama kali terlihat.

> **Hasil:** 7.483 baris BMKG menjadi **6.492 baris unik** dari 35 terbitan.

### 4.4 Validasi rentang dan karantina

Setiap kolom angka punya rentang wajar. Baris yang melanggar **tidak diperbaiki**; baris itu dipindah ke karantina dengan alasan yang jelas. Fungsinya `split_invalid()`.

| Kolom | Rentang | | Kolom | Rentang |
|---|---|---|---|---|
| `precip_mm` (BMKG, per 3 jam) | 0–500 | | `precip_mm` (Open-Meteo, per jam) | 0–300 |
| `temperature_c` | −5–45 | | `humidity_pct`, `cloud_cover_pct`, `precip_prob_pct` | 0–100 |
| `pressure_hpa` | 900–1100 | | `wind_dir_deg` | 0–360 |

`NaN` **tidak** dianggap pelanggaran. Kosong berarti "tidak tahu", bukan "salah".

### 4.5 Laporan banjir: dari 119 ribu menjadi 11 ribu

Arsip PetaBencana berisi **119.344 laporan** se-Indonesia untuk semua jenis bencana. Semuanya berstatus `confirmed`, termasuk laporan latihan. Penyaringannya ([`pipeline/clean/petabencana.py`](../pipeline/clean/petabencana.py)):

```mermaid
flowchart TD
    A["119.344 laporan<br/>semua bencana, se-Indonesia"] -->|"banjir + Jabodetabek<br/>(kode wilayah BPS, atau kotak koordinat<br/>kalau kode kosong)"| B["23.981 laporan banjir Jabodetabek"]
    B -->|"teks latihan/uji<br/>HKB, simulasi, gladi, tes…"| X1["11.495 ditandai"]
    B -->|"partner_code = tescode"| X2["217 ditandai"]
    B -->|"ledakan: ≥10 laporan dalam satu sel ±5 km<br/>per jam dengan foto <50%, atau ≥25 laporan"| X3["1.108 ditandai"]
    B --> OK["11.161 laporan dipakai"]
```

Laporan yang ditandai **tetap disimpan** dengan kolom `exclusion_reason`, supaya UI bisa jujur menyebut *"42 laporan disaring sebagai latihan dalam 12 bulan terakhir"*. Lebih dari separuh laporan banjir di arsip ternyata latihan atau uji. Inilah alasan status `confirmed` tidak bisa dipercaya begitu saja.

---

## 5. Load: memuat ke PostgreSQL

Kode: [`pipeline/db.py`](../pipeline/db.py), skema: [`sql/schema.sql`](../sql/schema.sql). Database: PostgreSQL 16 + PostGIS lewat Docker.

Pemuatan memakai tabel staging sementara supaya satu job cukup satu kali bolak-balik ke database:

```sql
-- 1. pandas: df.to_sql("_stg_forecast_hourly", ...)
-- 2. pindahkan yang belum ada saja
INSERT INTO forecast_hourly (...) SELECT ... FROM _stg_forecast_hourly
ON CONFLICT (location, issued_at, valid_at) DO NOTHING;
-- 3. DROP TABLE _stg_forecast_hourly
```

- **Kunci unik** tiap tabel menentukan apa yang dianggap "baris yang sama", misalnya `(location, analysis_at, valid_at)` untuk BMKG. Karena itu menjalankan ulang aman. Eksekusi kedua hari ini menghasilkan `masuk 0` di semua job.
- **Pengecualian:** di `flood_reports`, kolom `exclusion_reason` boleh berubah. Laporan baru di sel-jam yang sama bisa mengubah status "ledakan" laporan lama, jadi dipakai `ON CONFLICT DO UPDATE ... WHERE ... IS DISTINCT FROM ...`, yang hanya memperbarui baris yang benar-benar berubah.
- `flood_reports.geom` adalah kolom PostGIS `GEOMETRY(Point, 4326)` yang dihitung otomatis dari `lon` dan `lat`. Kolom ini siap dipakai nanti untuk menggabungkan laporan dengan poligon kecamatan.

---

## 6. Transformasi SQL: view analitik

Kode: [`sql/views.sql`](../sql/views.sql). Logika yang lebih alami dalam SQL ditulis sebagai view, dan dibuat ulang setiap job `views` berjalan.

| View | Pertanyaan yang dijawab | Teknik |
|---|---|---|
| `v_hourly_runs` | Run Open-Meteo mana yang terbaru, mana yang sebelumnya? | `GROUP BY` + `DENSE_RANK() OVER (PARTITION BY location ORDER BY issued_at DESC)` |
| `v_forecast_change` | Berapa selisih prakiraan run terbaru dan sebelumnya pada jam yang sama? | CTE `latest` dan `previous` + `LEFT JOIN` pada `valid_at` |
| `v_bmkg_latest` | Apa isi terbitan BMKG terakhir per kota? | Subquery `MAX(analysis_at)` + `JOIN ... USING` |
| `v_obs_rolling` | Berapa hujan 3 dan 7 hari terakhir? Masuk kategori apa? | `SUM() OVER (... RANGE BETWEEN INTERVAL '2 days' PRECEDING ...)` + fungsi `bmkg_category()` (`CASE WHEN`) |
| `v_flood_reports_daily` | Berapa laporan dipakai dan disaring per hari? | `COUNT(*) FILTER (WHERE ...)` |
| `v_source_freshness` | Kapan tiap sumber terakhir masuk, berapa kota yang berhasil? | CTE + `FILTER` + jendela 10 menit, karena BMKG diambil per kota dengan jeda 1 detik |

Contoh: perubahan prakiraan Jakarta untuk 24 jam ke depan menunjukkan **9,7 mm → 14,6 mm** antara run pukul 04.48 dan 09.48 WIB.

---

## 7. Pencatatan dan karantina

**`ingest_runs`.** Setiap job dibungkus kelas `JobRun` (context manager). Kelas ini mencatat waktu mulai dan selesai, status (`ok` atau `failed`), jumlah baris dibaca, masuk, dan ditolak, serta keterangan. Satu job yang gagal tidak menghentikan job lain. Tabel inilah yang ditampilkan di halaman **Status**.

**`quarantine`.** Baris yang ditolak disimpan sebagai `jsonb` beserta alasannya. Ada kolom `record_hash = md5(record)` dengan constraint `UNIQUE (job, record_hash)`, sehingga baris yang sama tidak dikarantina dua kali saat job dijalankan ulang.

Isi karantina hari ini:

| Job | Alasan | Jumlah |
|---|---|---:|
| `forecast_bmkg` | BMKG membalas tanpa prakiraan (`"cuaca": null`), 21 Nov 02.19 UTC, 8 kota | 8 |
| `forecast_openmeteo` | Timeout ke `api.open-meteo.com` (3 run × 8 kota) | 24 |

---

## 8. Menyajikan: dari API ke layar

Kode: [`api/main.py`](../api/main.py), [`api/logic.py`](../api/logic.py), [`web/index.html`](../web/index.html).

| Endpoint | Isi | Dipakai di |
|---|---|---|
| `GET /api/cities` | Total hujan 24 jam ke depan per kota | Daftar kota di dasbor |
| `GET /api/forecast/{kota}` | 24 jam per jam (run terbaru vs sebelumnya), ringkasan, prakiraan BMKG per 3 jam | Judul, grafik "tirai hujan", strip BMKG |
| `GET /api/map` | Semua kota dengan 24 jam datanya, satu panggilan | Animasi di halaman Peta |
| `GET /api/floods` | Kepadatan laporan per sel 0,05°, ranking wilayah, laporan terbaru | Bagian bawah "garis air", lapisan peta |
| `GET /api/history/{kota}` | Hujan harian ERA5 + akumulasi 3 dan 7 hari | Disiapkan untuk agen dan Model A |
| `GET /api/status` | Kesegaran sumber, job terakhir, karantina | Halaman Status |
| `POST /api/admin/refresh` | Menjalankan pipeline di latar belakang | Dilindungi header `X-API-Key` |

Semua waktu dikirim dalam ISO 8601 di zona lokal kota (`+07:00` WIB, `+08:00` WITA), jadi frontend tidak perlu menebak zona waktu.

### Contoh: dari mana kalimat di judul dasbor berasal

> *"Jakarta diprakirakan hujan ringan mulai pukul 12.00, paling deras sekitar 16.00 WIB."*

Kalimat ini **bukan prediksi model ML SIAGA NUSA**, dan juga bukan teks statis. Fungsi `summarize()` menghitungnya dari 24 jam prakiraan Open-Meteo:

| Bagian kalimat | Aturan |
|---|---|
| "hujan ringan" | Total 24 jam (14,6 mm) dicocokkan dengan kategori harian BMKG: 0,5–20 mm = ringan |
| "mulai pukul 12.00" | Jam pertama dengan hujan ≥0,5 mm/jam |
| "paling deras sekitar 16.00" | Jam dengan angka hujan terbesar (2,6 mm) |

Fungsi `headline()` di frontend menyusunnya menjadi kalimat. Tepat di bawahnya UI menuliskan sumbernya: *"Disusun otomatis dari prakiraan per jam Open-Meteo …, bukan prediksi model SIAGA NUSA."*

---

## 9. Temuan dari data asli

| Temuan | Dampak ke desain |
|---|---|
| BMKG pernah membalas **HTTP 200 dengan isi prakiraan kosong** untuk 8 kota sekaligus (21 Nov) | Status HTTP tidak cukup untuk menilai respons; isinya juga harus diperiksa. Kasus ini kini dikarantina dan punya test |
| Open-Meteo **timeout** 3 kali dalam 17 hari | Snapshot mencoba ulang sekali setelah 60 detik; kegagalan tetap tercatat |
| GitHub Actions hanya menjalankan cron **±3 kali sehari**, walau dijadwalkan tiap jam | Perubahan prakiraan dibandingkan dengan run sebelumnya yang benar-benar ada, dan jam run itu ditulis di UI ("Dibanding pembaruan pukul 04.48 …") |
| ERA5 **tertinggal ±5 hari**, ERA5-Land lebih lama lagi | Hari tanpa data tidak disimpan; badge di UI menyebut "s.d. 17 Nov · tertinggal ±5 hari" |
| **>50% laporan banjir** di arsip adalah latihan atau uji, padahal berstatus `confirmed` | Tiga lapis penanda; laporan tetap disimpan dengan alasan |
| Laporan banjir Jabodetabek terakhir **25 Okt** | Bukan bug; musim kemarau baru selesai. Badge berwarna kuning karena datanya sudah lama |
| `bmkg_category()` di Python memberi `None` di bawah 0,5 mm, sedangkan versi SQL memberi "tidak hujan" | Ketahuan lewat unit test sebelum muncul sebagai "hujan null" di dasbor. Kini disamakan |

---

## 10. Angka per 23 November 2026

| Tabel | Baris | Rentang |
|---|---:|---|
| `raw_payloads` | 816 | 6–23 Nov 2026, 51 run |
| `forecast_bmkg` | 6.492 | 35 terbitan BMKG |
| `forecast_hourly` | 64.512 | 48 run sukses × 8 kota × 168 jam |
| `obs_daily` (ERA5) | 28.864 | 1 Jan 2017 – 17 Nov 2026 |
| `obs_daily` (ERA5-Land) | 28.728 | 1 Jan 2017 – 31 Okt 2026 |
| `flood_reports` | 23.981 | Des 2016 – Okt 2026 (11.161 dipakai) |
| `quarantine` | 32 | |

Ukuran database 48 MB. Satu eksekusi penuh `pipeline.run all` butuh ±35 detik.

---

## 11. Materi bootcamp yang dipakai

| Sesi | Materi | Dipakai di |
|---|---|---|
| 3 | Python dasar | Seluruh modul pipeline |
| 4 | Fungsi & OOP | Fungsi transform kecil yang bisa dites; kelas `JobRun` sebagai context manager; dataclass `Location` |
| 5 | Git & GitHub | Branch `data-snapshots` sebagai arsip data; `git fetch` + `git archive` di job `sync` |
| 6 | Data wrangling dengan pandas | Meratakan JSON, `to_datetime`, `to_numeric(errors="coerce")`, `drop_duplicates`, validasi rentang, pembersihan teks, penanda laporan latihan |
| 7 | Python automation | GitHub Actions terjadwal; CLI `argparse` (`python -m pipeline.run ...`); `logging` |
| 8 | SQL for AI | `GROUP BY`, `JOIN`, CTE, window function, `FILTER`, `CASE WHEN`, index |
| 9 | Scraping & cleaning pipeline | `requests` dengan retry; `pydantic-settings` + `.env`; SQLAlchemy; `CREATE TABLE IF NOT EXISTS`; `ON CONFLICT` |
| 10 | API & FastAPI | Model respons Pydantic, `/health`, dokumentasi `/docs`, autentikasi `X-API-Key`, `BackgroundTasks` |
| 11 | End-to-end data pipeline | Jalur ETL dan ELT berdampingan; transformasi SQL setelah load; pipeline sampai disajikan lewat API |

---

## 12. Menjalankan

```bash
docker compose up -d db                  # PostgreSQL 16 + PostGIS di localhost:5434
python -m pipeline.run all               # semua job, berurutan
python -m pipeline.run forecasts views   # atau job tertentu saja
uvicorn api.main:app --port 8010         # dasbor http://localhost:8010 · /docs
pytest -q                                # 48 test unit, tanpa database
```

---

## 13. Yang belum

| Bagian | Status |
|---|---|
| Debit sungai GloFAS + indeks risiko banjir | Belum ditarik. Peta sementara menampilkan kepadatan laporan warga |
| Model A (peluang hujan ≥20 mm besok) | Label sudah ada di `v_obs_rolling.is_moderate_plus`; model belum dilatih |
| Peringatan dini BMKG (RSS/CAP) | Belum tersambung |
| Poligon kecamatan (PostGIS) | Wilayah masih memakai kode kab/kota dan sel grid 0,05° |
| Penjadwal di server | Pipeline masih dijalankan manual atau lewat `POST /api/admin/refresh` |
