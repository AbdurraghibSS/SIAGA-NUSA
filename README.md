<div align="center">

<img src="assets/banner.svg" alt="SIAGA NUSA — Sistem Intelijen Agen Generatif untuk Analisis Cuaca dan Banjir Nusantara" width="100%"/>

<img src="https://img.shields.io/badge/Status-Dalam%20Pengembangan%20%C2%B7%20In%20Development-FF7A1A?style=for-the-badge" alt="Status"/> <img src="https://img.shields.io/badge/Final%20Project-Digital%20Skola%20%C3%97%20Microsoft%20Azure-1B2A6B?style=for-the-badge" alt="Final Project"/>

<img src="https://img.shields.io/badge/Agentic%20AI-D63384?style=flat-square" alt="Agentic AI"/> <img src="https://img.shields.io/badge/Weather%20%26%20Flood-0E7490?style=flat-square" alt="Weather & Flood"/> <img src="https://img.shields.io/badge/Bahasa%20Indonesia-CE1126?style=flat-square" alt="Bahasa Indonesia"/> <img src="https://img.shields.io/badge/Showcase-23%20Des%202026-FFB900?style=flat-square" alt="Showcase"/>

🇮🇩 Bahasa Indonesia &nbsp;·&nbsp; 🇬🇧 *English in italics*

</div>

---

<div align="justify">

## 🌧️ Tentang · *About*

**SIAGA NUSA** (*Sistem Intelijen Agen Generatif untuk Analisis Cuaca dan Banjir Nusantara*) adalah agen AI berbasis web yang membantu warga memahami cuaca dan risiko banjir. Agen menjawab dalam bahasa sehari-hari **hanya dari data**: prakiraan resmi dan model cuaca, prediksi model SIAGA NUSA, debit sungai, laporan warga, dan glosarium. Setiap informasi selalu disertai label sumber dan waktunya.<br>
*SIAGA NUSA (Generative Agent Intelligence System for Indonesian Weather and Flood Analysis) is a web-based AI agent that helps people understand the weather and flood risk. It answers in plain language **from data only**: official and model weather forecasts, SIAGA NUSA model predictions, river discharge, citizen reports, and a glossary. Every piece of information is labelled with its source and time.*

<blockquote>
<h3 align="center"><i>"Lebih Cepat Memahami. Lebih Siap Menghadapi."</i></h3>
<p align="center"><i>"Understand Faster. Be Better Prepared."</i></p>
</blockquote>

## ❓ Masalah · *The Problem*

> *Rabu sore, 4 November 2026, di Jakarta. Langit mendung, dan grup keluarga bertanya: "Nanti malam hujan lebat nggak? Kemarin Kemang banjir, besok bakal banjir lagi?" Lalu muncul pesan berantai: "BMKG: Jakarta siaga banjir besok, segera ungsikan barang!"*<br>
> *Wednesday afternoon, 4 November 2026, in Jakarta. The sky is overcast, and the family group chat asks: "Will it rain heavily tonight? Kemang flooded yesterday, will it flood again tomorrow?" Then a chain message appears: "BMKG: Jakarta on flood alert tomorrow, move your belongings now!"*

- **Prakiraan tersebar dan teknis.** Prakiraan per kelurahan ada di BMKG, prakiraan per jam ada di model cuaca global, dan debit sungai ada di GloFAS.<br>
  *Forecasts are scattered and technical. Per-village forecasts live at BMKG, hourly forecasts in global weather models, and river discharge in GloFAS.*
- **Prakiraan berubah tanpa jejak.** Aplikasi cuaca biasa tidak menunjukkan apa yang berubah sejak pembaruan sebelumnya.<br>
  *Forecasts change without a trace. Typical weather apps don't show what changed since the previous update.*
- **Laporan banjir warga cepat tapi belum terverifikasi**, sementara kabar palsu menyebar lebih cepat daripada data resmi.<br>
  *Citizen flood reports are fast but unverified, while false alerts spread faster than official data.*

## 💡 Solusi · *The Solution*

| Komponen · *Component* | Fungsi · *Purpose* |
|---|---|
| 🌦️ **Weather Monitoring & Change Tracking** | Memantau prakiraan kota pilot dan menunjukkan apa yang berubah dibanding pembaruan sebelumnya.<br>*Monitors forecasts for pilot cities and shows what changed since the previous update.* |
| 🌧️ **Model A — Rainfall Prediction** | Memprediksi peluang hujan **sedang–lebat (≥20 mm/hari)** esok hari, mengikuti kategori intensitas hujan BMKG.<br>*Predicts the probability of **moderate-to-heavy rain (≥20 mm/day)** tomorrow, following BMKG's rainfall intensity categories.* |
| 🌊 **Model B — Flood Occurrence Prediction** | Memprediksi peluang banjir per kecamatan Jabodetabek pada H+1, **bila lolos uji kelayakan data** di minggu ke-2.<br>*Predicts the probability of flooding per Jabodetabek district on the next day, **if it passes the data go/no-go gate** in week 2.* |
| 🤖 **SIAGA NUSA AI Agent** | Agen Gemini yang memilih tool sendiri, menjawab langsung, atau menolak, tanpa pernah mengarang angka.<br>*A Gemini agent that picks its own tools, answers directly, or declines, without ever inventing numbers.* |
| 🖥️ **Antarmuka · *Interface*** | Web (HTML/JS) yang disajikan FastAPI: Dasbor (cuaca di atas "garis air", laporan banjir di bawahnya), Peta cuaca (animasi hujan per jam + radar + laporan banjir), Status, dan widget Tanya di kanan bawah.<br>*Web app (HTML/JS) served by FastAPI: Dashboard, Weather map (hourly rain animation + radar + flood reports), Status, and an Ask widget in the bottom-right corner.* |

### 🏷️ Setiap informasi berlabel sumber · *Every answer is source-labelled*

| Label | Artinya · *Meaning* |
|---|---|
| 🟢 **RESMI** · *Official* | Langsung dari data BMKG · *Straight from BMKG data* |
| 🔵 **DATA MODEL CUACA** · *Weather model data* | Open-Meteo / GloFAS. Berguna, tapi bukan pernyataan resmi · *Useful, but not an official statement* |
| 🤖 **PREDIKSI SIAGA NUSA** · *Prediction* | Keluaran Model A/B, selalu dengan peluang dan versi model · *Model A/B output, always with probability and model version* |
| 🟡 **LAPORAN WARGA** · *Citizen report* | Laporan PetaBencana, belum terverifikasi sampai ada konfirmasi silang · *PetaBencana reports, unverified until cross-confirmed* |
| 📘 **GLOSARIUM** · *Glossary* | Istilah cuaca dan panduan banjir · *Weather terms and flood guidance* |

## 🗺️ Cakupan · *Scope*

| Inti · *Core* | Tambahan, setelah live · *Extra, after go-live* |
|---|---|
| 🌦️ Prakiraan & perubahan prakiraan 8 kota pilot · *Forecasts & forecast changes for 8 pilot cities*<br>🌧️ Prediksi hujan sedang–lebat · *Moderate-to-heavy rain prediction*<br>🌊 Laporan banjir warga + debit sungai Jabodetabek · *Citizen flood reports + river discharge in Jabodetabek* | 📉 Anomali hujan · *Rainfall anomalies*<br>🟢 Peringatan dini cuaca BMKG · *BMKG weather warnings*<br>📝 Ringkasan harian · *Daily summary* |

**Kota pilot · *Pilot cities*:** Jakarta, Bogor, Bandung, Semarang, Yogyakarta, Surabaya, Medan, Makassar ([`pipeline/locations.py`](pipeline/locations.py)).

## 🛡️ Prinsip Keamanan · *Safety Principle*

> **"LLM tidak pernah memegang tombol sirene."**<br>
> *"The LLM never holds the siren button."*

Status siaga dan peringatan resmi **hanya** berasal dari data BMKG dan diputuskan oleh kode, bukan oleh model bahasa. Laporan warga dan pesan pengguna selalu diperlakukan sebagai data, bukan perintah, sehingga sistem tahan terhadap *prompt injection* seperti upaya menyebarkan peringatan banjir palsu.<br>
*Alert status and official warnings come **only** from BMKG data and are decided by code, never by the language model. Citizen reports and user messages are always treated as data, not instructions, so the system resists prompt injection such as attempts to spread fake flood warnings.*

## 🧰 Tech Stack

<div align="center">

<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/> <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/> <img src="https://img.shields.io/badge/Gemini%20API-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white" alt="Gemini API"/> <img src="https://img.shields.io/badge/PostgreSQL%20%2B%20PostGIS-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL + PostGIS"/> <img src="https://img.shields.io/badge/Qdrant-DC244C?style=for-the-badge&logo=qdrant&logoColor=white" alt="Qdrant"/> <img src="https://img.shields.io/badge/scikit--learn%20%2F%20XGBoost-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white" alt="scikit-learn / XGBoost"/> <img src="https://img.shields.io/badge/MLflow-0194E2?style=for-the-badge&logo=mlflow&logoColor=white" alt="MLflow"/> <img src="https://img.shields.io/badge/pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" alt="pandas"/> <img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy"/> <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/> <img src="https://img.shields.io/badge/Azure%20VM-0078D4?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGQ9Ik01LjQ4MyAyMS4zSDI0TDE0LjAyNSA0LjAxM2wtMy4wMzggOC4zNDcgNS44MzYgNi45MzhMNS40ODMgMjEuM3pNMTMuMjMgMi43TDYuMTA1IDguNjc3IDAgMTkuMjUzaDUuNTA1di4wMTRMMTMuMjMgMi43eiIvPjwvc3ZnPg%3D%3D" alt="Azure VM"/>

</div>

## 📡 Sumber Data · *Data Sources*

| Sumber · *Source* | Data | Lisensi · *License* |
|---|---|---|
| [BMKG](https://data.bmkg.go.id/) | Prakiraan cuaca per kelurahan, peringatan dini cuaca · *Per-village forecasts, weather warnings* | Wajib mencantumkan BMKG · *BMKG attribution required* |
| [Open-Meteo](https://open-meteo.com/) | Prakiraan per jam, historis ERA5, *historical forecast*, *previous runs*, debit sungai GloFAS · *Hourly forecasts, ERA5 history, historical forecasts, previous runs, GloFAS river discharge* | CC BY 4.0 |
| [PetaBencana.id](https://petabencana.id/) | Laporan banjir warga · *Citizen flood reports* | Atribusi · *Attribution* |
| [RainViewer](https://www.rainviewer.com/) | Lapisan radar hujan di peta (observasi, cakupan Indonesia terbatas) · *Rain radar map layer* | Atribusi · *Attribution* |
| [Esri](https://www.esri.com/) | Peta dasar Dark Gray · *Dark Gray basemap* | Atribusi · *Attribution* |
| BNPB, BMKG, BPBD DKI, Kemenkes, ESDM | 10 panduan kesiapsiagaan & definisi resmi (PDF) untuk RAG agen Tanya, daftar di [`pipeline/knowledge.py`](pipeline/knowledge.py). PDF tidak di-commit · *Preparedness guides for the agent's RAG; PDFs are not committed* | Hak cipta penerbit · *Publisher's copyright* |

## 🚀 Menjalankan · *Running*

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
pytest -q

docker compose up -d --build               # db + qdrant + backend + frontend, ikut naik setiap Docker hidup
python -m pipeline.run all                 # sync snapshot → muat → bersihkan → view SQL → prediksi
python -m pipeline.run knowledge           # RAG: PDF panduan di docs/ → embedding Gemini → Qdrant
```

| Container | Isi | Alamat |
|---|---|---|
| `db` | PostgreSQL 16 + PostGIS | `localhost:5434` |
| `qdrant` | Vector DB Qdrant: potongan panduan resmi + embedding untuk RAG | `127.0.0.1:6333` |
| `backend` | FastAPI: `/api`, `/api/chat` (agen), `/health`, `/docs` | `127.0.0.1:8011` |
| `frontend` | nginx: dasbor `web/`, meneruskan `/api` & `/docs` ke backend | **http://localhost:8010** |

Mengubah `web/` atau kode backend? Jalankan ulang `docker compose up -d --build`. Untuk pengembangan cepat tanpa Docker, `uvicorn api.main:app --reload --port 8010` tetap menyajikan API dan dasbor sekaligus (hentikan dulu container `frontend` karena memakai port yang sama).<br>
*All three containers restart with Docker. The frontend (nginx) serves the dashboard and proxies `/api` to the backend; rebuild after changes.*

Snapshot prakiraan dikumpulkan otomatis oleh GitHub Actions (dijadwalkan tiap jam; kenyataannya ±3 kali sehari karena GitHub sering menunda cron) ([`snapshot.yml`](.github/workflows/snapshot.yml)) ke branch [`data-snapshots`](https://github.com/AbdurraghibSS/SIAGA-NUSA/tree/data-snapshots), karena BMKG tidak menyediakan arsip prakiraan. `pipeline.run sync` mengambil branch itu.<br>
*Forecast snapshots are collected by GitHub Actions (scheduled hourly; in practice ±3 times a day because GitHub often delays cron) into the `data-snapshots` branch, because BMKG keeps no forecast archive. `pipeline.run sync` pulls that branch.*

### 🔁 Alur data · *Data flow*

| Job | Pola · *Pattern* | Isi · *What it does* |
|---|---|---|
| `sync` | Extract | `git fetch` + `git archive` branch `data-snapshots` → `data/snapshots/` |
| `raw` | ELT | Envelope JSON apa adanya → `raw_payloads` (`jsonb`), termasuk yang gagal · *Raw envelopes, failures included* |
| `forecasts` | ETL (pandas) | Ratakan JSON, konversi tipe & zona waktu, buang duplikat terbitan BMKG, nilai di luar rentang → `quarantine`. Nilai kosong tidak diisi tebakan · *Flatten, cast, dedupe, quarantine out-of-range values; missing values are never imputed* |
| `history` | ETL | Hujan harian ERA5 dari arsip + susul hari yang belum ada lewat API · *ERA5 daily backfill + incremental catch-up* |
| `floods` | ETL | Arsip PetaBencana bulan berjalan ditarik ulang, laporan latihan/uji/ledakan ditandai · *Refresh current month, flag drill/test/burst reports* |
| `archive` | ETL | Prakiraan yang terbit **sehari sebelumnya** dari 4 model (Open-Meteo Previous Runs) untuk fitur Model A · *Day-before forecasts from 4 models for Model A features* |
| `predict` | ML | Peluang hujan ≥20 mm besok per kota dari `siaganusa-hujan@champion` (MLflow) → `rain_predictions` · *Tomorrow's ≥20 mm rain probability from the champion model* |
| `rivers` | ETL | Debit sungai GloFAS per kota (riwayat 2010–sekarang + prakiraan 7 hari) · *GloFAS river discharge per city (2010–now + 7-day forecast)* |
| `views` | SQL | CTE, window function (`DENSE_RANK`, `SUM OVER`), `FILTER`, `CASE WHEN` di [`sql/views.sql`](sql/views.sql) |
| `knowledge` | RAG | PDF panduan → potongan 200 kata (tumpang tindih 40) → vektor dense `multilingual-e5-small` (384 dim) + sparse BM25, keduanya lokal (FastEmbed, tanpa kuota API) → Qdrant. Pencarian hybrid (RRF): 7/8 relevan di top-3 vs dense 5/8, BM25 6/8. Dijalankan manual · *Hybrid dense + BM25 local embeddings in Qdrant; run manually* |

Semua job idempotent (`ON CONFLICT`), dan setiap eksekusi tercatat di `ingest_runs` untuk halaman Status.<br>
*All jobs are idempotent (`ON CONFLICT`), and every run is logged in `ingest_runs` for the Status page.*

📄 Penjelasan lengkap · *Full walkthrough*: [`docs/data-processing.md`](docs/data-processing.md)<br>
🔢 Dasar setiap ambang & bobot · *Where every threshold and weight comes from*: [`docs/dasar-angka.md`](docs/dasar-angka.md)

### 💬 Agen Tanya · *Ask agent*

`POST /api/chat` → Gemini (`gemini-3.8-flash`) memilih dari 8 tool read-only, maksimal 5 putaran, lalu menjawab dengan label sumber. Kodenya di [`api/agent/`](api/agent/).<br>
*Gemini picks from 8 read-only tools (max 5 rounds) and answers with source labels.*

| Tool | Data |
|---|---|
| `get_weather_forecast` | Open-Meteo 24 jam + prakiraan resmi BMKG per 3 jam, satu kota |
| `get_cities_overview` | Total hujan 24 jam di 8 kota |
| `get_rain_chance_tomorrow` | Model A: peluang hujan ≥20 mm besok |
| `get_flood_risk` | Indeks risiko banjir + komponennya |
| `get_river_conditions` | Debit sungai GloFAS |
| `get_flood_reports` | Laporan warga PetaBencana (Jabodetabek) |
| `get_rain_history` | Hujan ERA5 yang sudah terjadi |
| `search_preparedness_guide` | RAG: 10 panduan resmi (BNPB, BMKG, BPBD DKI, Kemenkes, ESDM) di Qdrant |

Pengaman · *Guardrails*: pola prompt injection ditolak sebelum memanggil Gemini, teks warga dibungkus `<data_warga>`, argumen tool divalidasi (kota di luar pilot → error terstruktur), tidak ada tool tulis/SQL bebas, setiap angka di jawaban dicocokkan dengan hasil tool, istilah Waspada/Siaga/Awas ditandai, batas 10 pertanyaan/menit/IP, dan setiap percakapan tercatat di `agent_logs`.

Hemat kuota Gemini gratis · *Free-tier quota*: (1) pertanyaan pembuka yang sama dijawab dari cache 10 menit; (2) model kena 429 → istirahat 60 detik, pindah ke `gemini-3.5-flash-lite`; (3) semua model habis atau kunci kosong → **mode hemat** tanpa LLM ([`api/agent/fallback.py`](api/agent/fallback.py)): maksud pertanyaan dikenali dengan kata kunci, tool yang sama dipanggil, jawaban dari template. Embedding RAG lokal, jadi pencarian panduan tidak pernah memakai kuota.

## 🚧 Status & Roadmap

Proyek ini sedang dikembangkan (30 Oktober – 23 Desember 2026).<br>
*This project is under active development (30 October – 23 December 2026).*

- [x] Ide & perencanaan · *Idea & planning*
- [x] Snapshot prakiraan BMKG + Open-Meteo terjadwal · *Scheduled BMKG + Open-Meteo forecast snapshots*
- [x] Backfill historis, pembersihan, skema Postgres + PostGIS · *Historical backfill, cleaning, Postgres + PostGIS schema*
- [x] API FastAPI + dasbor web dengan data asli · *FastAPI + web dashboard on real data*
- [x] Debit sungai GloFAS + indeks risiko banjir (API) · *GloFAS river discharge + flood risk index (API)*
- [x] Model A dilatih & terdaftar di MLflow (`siaganusa-hujan@champion`), [notebook 04](notebooks/04_model_a_hujan.ipynb) · *Model A trained & registered in MLflow*
- [x] Prediksi Model A di dasbor: peluang + kelas Rendah/Sedang/Tinggi (job `predict`) · *Model A predictions on the dashboard*
- [ ] Model B (bila lolos *gate*) · *Model B (if it passes the gate)*
- [x] Agen Gemini + 8 tools + RAG panduan resmi di Qdrant · *Gemini agent + 8 tools + RAG on official guides in Qdrant*
- [x] Widget Tanya di dasbor dengan "Lihat langkah agen" · *Ask widget with agent steps*
- [ ] Laporan situasi otomatis · *Automatic situation report*
- [x] `docker compose up`: db + backend + frontend · *db + backend + frontend containers*
- [ ] Deploy Azure VM · *Azure VM deployment*
- [ ] Uji keamanan prompt injection · *Prompt injection security testing*
- [ ] Showcase — 23 Desember 2026

## 🎓 Konteks · *Context*

Final Project untuk bootcamp **AI Engineer — Digital Skola × Microsoft Azure**. Catatan belajar selengkapnya ada di repo [AI-Engineer-Training-with-DigitalSkola](https://github.com/AbdurraghibSS/AI-Engineer-Training-with-DigitalSkola).<br>
*Final Project for the **AI Engineer — Digital Skola × Microsoft Azure** bootcamp. Full learning notes are in the [AI-Engineer-Training-with-DigitalSkola](https://github.com/AbdurraghibSS/AI-Engineer-Training-with-DigitalSkola) repo.*

</div>

> [!WARNING]
> SIAGA NUSA **bukan** sistem peringatan dini resmi. Saat cuaca ekstrem atau banjir, selalu ikuti informasi dari BMKG dan BPBD setempat.<br>
> *SIAGA NUSA is **not** an official early-warning system. During extreme weather or floods, always follow BMKG and your local disaster management agency (BPBD).*
