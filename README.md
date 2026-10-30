<div align="center">

<img src="assets/banner.svg" alt="SIAGA NUSA — Sistem Intelijen Agen Generatif untuk Analisis Bencana Nusantara" width="100%"/>

<img src="https://img.shields.io/badge/Status-Dalam%20Pengembangan%20%C2%B7%20In%20Development-FF7A1A?style=for-the-badge" alt="Status"/> <img src="https://img.shields.io/badge/Final%20Project-Digital%20Skola%20%C3%97%20Microsoft%20Azure-1B2A6B?style=for-the-badge" alt="Final Project"/>

<img src="https://img.shields.io/badge/Agentic%20AI-D63384?style=flat-square" alt="Agentic AI"/> <img src="https://img.shields.io/badge/Disaster%20Intelligence-FF3D3D?style=flat-square" alt="Disaster Intelligence"/> <img src="https://img.shields.io/badge/Bahasa%20Indonesia-CE1126?style=flat-square" alt="Bahasa Indonesia"/> <img src="https://img.shields.io/badge/Showcase-23%20Des%202026-FFB900?style=flat-square" alt="Showcase"/>

🇮🇩 Bahasa Indonesia &nbsp;·&nbsp; 🇬🇧 *English in italics*

</div>

---

<div align="justify">

## 🚨 Tentang · *About*

**SIAGA NUSA** (*Sistem Intelijen Agen Generatif untuk Analisis Bencana Nusantara*) adalah agen AI yang membantu masyarakat memahami situasi bencana dengan cepat. Agen menjawab dalam bahasa sehari-hari, lewat web dan Telegram, dengan menggabungkan data resmi, prediksi model, dan laporan warga. Setiap informasi selalu disertai label sumbernya.<br>
*SIAGA NUSA (Generative Agent Intelligence System for Indonesian Disaster Analysis) is an AI agent that helps people quickly understand disaster situations. It answers in plain language, on the web and Telegram, by combining official data, model predictions, and citizen reports. Every piece of information is always labelled with its source.*

<blockquote>
<h3 align="center"><i>"Lebih Cepat Memahami. Lebih Siap Menghadapi."</i></h3>
<p align="center"><i>"Understand Faster. Be Better Prepared."</i></p>
</blockquote>

## ❓ Masalah · *The Problem*

> *Kamis pagi, 29 Oktober 2026: gempa M6.0 mengguncang Papua. Beberapa menit kemudian, pesan berantai "BMKG: waspada tsunami susulan!" mulai beredar. Kenyataannya gempa itu terjadi di darat, dan BMKG tidak pernah mengeluarkan peringatan tsunami.*<br>
> *Thursday morning, 29 October 2026: an M6.0 earthquake struck Papua. Minutes later, chain messages saying "BMKG: beware of an aftershock tsunami!" began to spread. In fact the quake was inland, and BMKG never issued a tsunami warning.*

- **Informasi resmi tersebar dan teknis.** Gempa, peringatan dini cuaca, prakiraan, dan tinggi gelombang ada di sumber yang berbeda-beda, dengan istilah seperti MMI, LS/BT, dan kedalaman hiposenter.<br>
  *Official information is scattered and technical. Earthquakes, weather warnings, forecasts, and wave heights live in different sources, full of jargon such as MMI, latitude/longitude, and hypocentre depth.*
- **Laporan warga cepat tapi belum terverifikasi.** Laporan ini sangat berguna untuk melihat kondisi lapangan, tapi juga bisa disalahgunakan.<br>
  *Citizen reports are fast but unverified. They are valuable for seeing conditions on the ground, but they can also be abused.*
- **Kabar palsu menyebar lebih cepat** daripada orang sempat membuka situs resmi.<br>
  *False alerts spread faster than people can check official sources.*

## 💡 Solusi · *The Solution*

| Komponen · *Component* | Fungsi · *Purpose* |
|---|---|
| 🌋 **Model A — Earthquake Impact Prediction** | Memprediksi apakah guncangan gempa mencapai intensitas **MMI ≥ V** (terasa kuat, berpotensi merusak).<br>*Predicts whether an earthquake's shaking reaches **MMI ≥ V** (strong, potentially damaging).* |
| 🌊 **Model B — Flood Occurrence Prediction** | Memprediksi peluang banjir per wilayah dalam **24 jam** ke depan, bila data historis dan curah hujannya memadai.<br>*Predicts the probability of flooding per area within the next **24 hours**, provided the historical and rainfall data are sufficient.* |
| 🤖 **SIAGA NUSA AI Agent** | Menggabungkan keluaran model, mengambil informasi resmi terbaru, menjelaskan hasil prediksi, dan menyusun **ringkasan situasi** berdasarkan sumbernya.<br>*Combines model outputs, fetches the latest official information, explains predictions, and builds source-labelled **situation summaries**.* |
| 💬 **Kanal · *Channels*** | Aplikasi web dengan peta interaktif, dan bot Telegram untuk bertanya maupun berlangganan info per wilayah.<br>*A web app with an interactive map, and a Telegram bot for questions and per-area subscriptions.* |

### 🏷️ Setiap informasi berlabel sumber · *Every answer is source-labelled*

| Label | Artinya · *Meaning* |
|---|---|
| 🟢 **RESMI** · *Official* | Langsung dari data BMKG · *Straight from BMKG data* |
| 🔵 **DATA CUACA** · *Weather data* | Data model cuaca global · *Global weather model data* |
| 🤖 **PREDIKSI** · *Prediction* | Keluaran model SIAGA NUSA, beserta peluangnya · *SIAGA NUSA model output, with its probability* |
| 🟡 **LAPORAN WARGA** · *Citizen report* | Laporan warga, belum terverifikasi sampai ada konfirmasi silang · *Unverified until cross-confirmed* |
| 📘 **PANDUAN** · *Guide* | Panduan keselamatan · *Safety guidance* |

## 🗺️ Cakupan Bencana · *Hazard Coverage*

| Inti · *Core* | Tambahan · *Extended* |
|---|---|
| 🌋 Gempa & tsunami · *Earthquakes & tsunamis*<br>🌊 Banjir · *Floods*<br>🌧️ Hujan lebat, ⚡ petir, 💨 angin kencang · *Heavy rain, lightning, strong winds* | 🌊 Ombak tinggi · *High waves*<br>☀️ Kekeringan · *Drought*<br>🔥 Karhutla & asap · *Forest fires & haze*<br>🌋 Gunung api · *Volcanoes* |

## 🛡️ Prinsip Keamanan · *Safety Principle*

> **"LLM tidak pernah memegang tombol sirene."**<br>
> *"The LLM never holds the siren button."*

Status tsunami dan peringatan resmi **hanya** berasal dari data BMKG dan diputuskan oleh kode, bukan oleh model bahasa. Laporan warga dan pesan pengguna selalu diperlakukan sebagai data, bukan perintah, sehingga sistem tahan terhadap *prompt injection* seperti upaya menyebarkan peringatan tsunami palsu.<br>
*Tsunami status and official warnings come **only** from BMKG data and are decided by code, never by the language model. Citizen reports and user messages are always treated as data, not instructions, so the system resists prompt injection such as attempts to spread fake tsunami warnings.*

## 🧰 Tech Stack

<div align="center">

<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/> <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/> <img src="https://img.shields.io/badge/LangChain%20%2F%20LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangChain / LangGraph"/> <img src="https://img.shields.io/badge/Azure%20OpenAI-0078D4?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGQ9Ik01LjQ4MyAyMS4zSDI0TDE0LjAyNSA0LjAxM2wtMy4wMzggOC4zNDcgNS44MzYgNi45MzhMNS40ODMgMjEuM3pNMTMuMjMgMi43TDYuMTA1IDguNjc3IDAgMTkuMjUzaDUuNTA1di4wMTRMMTMuMjMgMi43eiIvPjwvc3ZnPg%3D%3D" alt="Azure OpenAI"/> <img src="https://img.shields.io/badge/PostgreSQL%20%2B%20PostGIS-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL + PostGIS"/> <img src="https://img.shields.io/badge/MLflow-0194E2?style=for-the-badge&logo=mlflow&logoColor=white" alt="MLflow"/> <img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge" alt="Next.js"/> <img src="https://img.shields.io/badge/MapLibre-396CB2?style=for-the-badge&logo=maplibre&logoColor=white" alt="MapLibre"/> <img src="https://img.shields.io/badge/Telegram%20Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram Bot"/> <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>

</div>

## 📡 Sumber Data · *Data Sources*

| Sumber · *Source* | Data |
|---|---|
| [BMKG](https://www.bmkg.go.id/) | Gempa terkini & status tsunami, peringatan dini cuaca, prakiraan cuaca · *Latest earthquakes & tsunami status, weather warnings, forecasts* |
| [USGS](https://earthquake.usgs.gov/) | Katalog gempa historis untuk melatih Model A · *Historical earthquake catalogue for training Model A* |
| [PetaBencana.id](https://petabencana.id/) | Laporan warga · *Citizen reports* |
| [Open-Meteo](https://open-meteo.com/) | Curah hujan, debit sungai, tinggi gelombang · *Rainfall, river discharge, wave height* |

## 🚧 Status & Roadmap

Proyek ini sedang dikembangkan (30 Oktober – 23 Desember 2026).<br>
*This project is under active development (30 October – 23 December 2026).*

- [x] Ide & perencanaan · *Idea & planning*
- [ ] Pipeline data otomatis · *Automated data pipeline*
- [ ] Model A & Model B + experiment tracking (MLflow)
- [ ] Agen AI · *AI agent*
- [ ] Aplikasi web & bot Telegram · *Web app & Telegram bot*
- [ ] Deployment publik · *Public deployment*
- [ ] Uji keamanan prompt injection · *Prompt injection security testing*
- [ ] Showcase — 23 Desember 2026

## 🎓 Konteks · *Context*

Final Project untuk bootcamp **AI Engineer — Digital Skola × Microsoft Azure**. Catatan belajar selengkapnya ada di repo [AI-Engineer-Training-with-DigitalSkola](https://github.com/AbdurraghibSS/AI-Engineer-Training-with-DigitalSkola).<br>
*Final Project for the **AI Engineer — Digital Skola × Microsoft Azure** bootcamp. Full learning notes are in the [AI-Engineer-Training-with-DigitalSkola](https://github.com/AbdurraghibSS/AI-Engineer-Training-with-DigitalSkola) repo.*

</div>

> [!WARNING]
> SIAGA NUSA **bukan** sistem peringatan dini resmi. Saat terjadi bencana, selalu ikuti informasi dari BMKG dan BPBD setempat.<br>
> *SIAGA NUSA is **not** an official early-warning system. During a disaster, always follow BMKG and your local disaster management agency (BPBD).*
