"""Mode hemat (plan §7.5) · dipakai saat kuota Gemini habis (HTTP 429) untuk semua model.

Tanpa LLM: maksud pertanyaan dikenali dengan kata kunci, tool yang sama dipanggil, lalu
jawaban disusun dari template. Hasilnya kaku tetapi angkanya tetap dari data, dan
pencarian panduan tetap jalan karena embedding dihitung lokal (FastEmbed), bukan di Gemini.
"""

import re
import time

from api.agent import tools
from api.agent.core import AgentResult, Step

NOTES = {
    "quota": "Mode hemat: layanan AI sedang penuh atau kuotanya habis, jadi jawaban ini disusun otomatis dari data tanpa AI.",
    "off": "Mode hemat: AI belum diaktifkan di server ini, jadi jawaban ini disusun otomatis dari data tanpa AI.",
    "error": "Mode hemat: layanan AI sedang bermasalah, jadi jawaban ini disusun otomatis dari data tanpa AI.",
    "limit": "Mode hemat: batas harian pertanyaan AI sudah tercapai, jadi jawaban ini disusun otomatis dari data tanpa AI.",
}

_WARN = re.compile(r"\b(peringatan|waspada|siaga|awas|status|hoaks|hoax|pesan berantai)\b", re.I)
_GUIDE = re.compile(r"\b(apa yang|harus|bagaimana|gimana|cara|siapkan|disiapkan|persiapan|tas siaga|evakuasi|mengungsi|"
                    r"lakukan|kesehatan|penyakit|leptospirosis|diare|longsor|arti|apa itu|maksud|istilah|status)\b", re.I)
_RISK = re.compile(r"\b(rawan|risiko|resiko|bahaya|paling)\b", re.I)
_TOMORROW = re.compile(r"\bbesok\b", re.I)
_RAIN = re.compile(r"\b(hujan|cuaca|deras|lebat|gerimis)\b", re.I)
_REPORTS = re.compile(r"\b(laporan|dilaporkan|kebanjiran|genangan)\b", re.I)


def _find_city(q: str) -> str | None:
    low = q.lower()
    for alias, slug in tools._ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", low):
            return slug
    for slug, name in tools.CITY_NAMES.items():
        if name.lower() in low:
            return slug
    return None


def _call(steps: list[Step], name: str, args: dict) -> dict:
    res, ms = tools.execute(name, args)
    steps.append(Step(tool=name, args=args, ms=round(ms), ok=bool(res.get("ok")), label=res.get("label"),
                      error=res.get("error")))
    return res


def keywords(query: str) -> set[str]:
    from pipeline.knowledge import words

    return words(query)


def rank_by_rare_words(passages: list[dict], query: str, idf=None) -> list[dict]:
    """Urutkan ulang potongan berdasarkan kata kunci pertanyaan yang dimuatnya, dibobot IDF dari
    SELURUH korpus (data/knowledge_df.json, ditulis job knowledge) lalu dikuadratkan, supaya satu kata
    langka ("leptospirosis") mengalahkan gabungan kata umum ("mencegah" + "banjir"). Urutan RRF untuk seri."""
    from pipeline import knowledge

    idf = idf or knowledge.idf
    weight = {w: idf(w) ** 2 for w in keywords(query)}  # kuadrat: satu kata langka > beberapa kata umum
    texts = [p["teks"].lower() for p in passages]
    return [p for _, p in sorted(((-sum(v for w, v in weight.items() if w in t), i), p)
                                 for i, (t, p) in enumerate(zip(texts, passages)))]


def snippet(text: str, query: str, size: int = 450) -> str:
    """Potong `text` di sekitar kata kunci pertanyaan yang paling jarang (paling informatif)
    yang muncul di teks, bukan sekadar awal potongan."""
    from pipeline import knowledge

    low = text.lower()
    found = sorted((-knowledge.idf(w), low.find(w)) for w in keywords(query) if w in low)
    pos = found[0][1] if found else 0
    start = max(0, pos - size // 4)
    if start > 0:  # mulai di awal kalimat kalau dekat, kalau tidak di awal kata
        dot = low.rfind(". ", 0, start)
        start = dot + 2 if dot >= 0 and dot > start - 120 else low.rfind(" ", 0, start) + 1
    cut = text[start:start + size].strip()
    return ("…" if start > 0 else "") + cut + ("…" if start + size < len(text) else "")


def _hm(iso: str | None) -> str:
    """'2026-11-26T04:00:00+07:00' → '04.00' (format jam Indonesia)."""
    return (iso or "")[11:16].replace(":", ".")


_BULAN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _date_hm(iso: str | None) -> str:
    """'2026-11-23T09:48:59+07:00' → '23 Nov 09.48' supaya data basi terlihat."""
    if not iso or len(iso) < 16:
        return "waktu tidak diketahui"
    return f"{int(iso[8:10])} {_BULAN[int(iso[5:7])]} {_hm(iso)}"


def _mm(x) -> str:
    return "–" if x is None else f"{x:.1f}".replace(".", ",")


def answer(question: str, reason: str = "quota") -> AgentResult:
    t0 = time.perf_counter()
    steps: list[Step] = []
    sources: list[dict] = []
    city = _find_city(question)
    lines: list[str] = []

    if _WARN.search(question) and not re.search(r"\b(tas siaga|siaga bencana|siapkan|disiapkan)\b", question, re.I):
        res = _call(steps, "get_official_warnings", {"city": city or "all"})
        if res.get("ok"):
            near = [(c["city"], p) for c in res["kota"] for p in c["peringatan"]]
            if near:
                lines.append(f"Peringatan dini cuaca BMKG yang berlaku (dibaca {_date_hm(res['as_of'])}):")
                lines += [f"- [Resmi BMKG] {cty}: {p['kejadian']} {_hm(p['berlaku_mulai'])}–{_hm(p['berlaku_sampai'])}, "
                          f"±{_mm(p['jarak_km_dari_titik_kota'])} km dari titik kota, di {', '.join(p['kecamatan_disebut'][:6])}"
                          f"{' dan lainnya' if p['total_kecamatan'] > 6 else ''}." for cty, p in near[:5]]
            else:
                where = tools.CITY_NAMES.get(city, "kota pilot") if city else "kota pilot"
                lines.append(f"[Resmi BMKG] Tidak ada peringatan dini cuaca BMKG yang berlaku di sekitar {where} "
                             f"(dibaca {_date_hm(res['as_of'])}). Itu bukan jaminan aman; pantau aplikasi InfoBMKG.")
    elif _GUIDE.search(question) and not (city and _RAIN.search(question) and not _RISK.search(question)):
        res = _call(steps, "search_preparedness_guide", {"query": question})
        if res.get("ok") and res.get("potongan"):
            lines.append("Kutipan panduan resmi yang paling relevan:")
            ranked = rank_by_rare_words(res["potongan"], question)
            for p in ranked[:2]:
                th = f" {p['tahun']}" if p.get("tahun") else ""
                lines.append(f"- [Panduan resmi] {snippet(p['teks'], question)} ({p['penerbit']}{th}, hlm. {p['halaman']})")
                sources.append({"title": p["judul"], "publisher": p["penerbit"], "year": p.get("tahun"),
                                "pages": str(p["halaman"])})
    elif _RISK.search(question) or (_REPORTS.search(question) is None and "banjir" in question.lower() and not city):
        res = _call(steps, "get_flood_risk", {"city": city or "all"})
        if res.get("ok"):
            rows = sorted([c for c in res["kota"] if c["skor"] is not None], key=lambda c: -c["skor"])
            lines.append(f"Indeks risiko banjir SIAGA NUSA (estimasi, bukan peringatan resmi), dihitung {_hm(res['as_of'])} WIB:")
            lines += [f"- [Prediksi SIAGA NUSA] {c['city']}: {c['skor']} ({c['level']})" for c in rows[:4]]
    elif _REPORTS.search(question):
        res = _call(steps, "get_flood_reports", {"days": 7})
        if res.get("ok"):
            lines.append(f"[Laporan warga] {res['laporan_7_hari']} laporan banjir di Jabodetabek dalam 7 hari terakhir "
                         f"(PetaBencana, belum terverifikasi).")
    elif _TOMORROW.search(question) and _RAIN.search(question) and not city:
        res = _call(steps, "get_rain_chance_tomorrow", {})
        if res.get("ok"):
            rows = sorted(res["kota"], key=lambda c: -c["peluang"])
            lines.append(f"Peluang hujan ≥20 mm untuk {res['target_tanggal']} (Model A):")
            lines += [f"- [Prediksi SIAGA NUSA] {c['city']}: {c['peluang_persen']}% ({c['kelas']})" for c in rows[:4]]
    elif city:
        res = _call(steps, "get_weather_forecast", {"city": city})
        if res.get("ok"):
            om = res.get("open_meteo_24_jam")
            if om:
                lines.append(f"[Data model cuaca] {res['city']}, 24 jam ke depan: total {_mm(om['total_mm'])} mm "
                             f"(kategori {om['kategori_bmkg_harian'] or 'tidak hujan'}), puncak {_mm(om['puncak_mm'])} mm "
                             f"sekitar pukul {_hm(om['puncak_jam'])} (run terbit {_date_hm(om['as_of'])}).")
            bm = res.get("bmkg_per_3_jam")
            if bm:
                blok = ", ".join(f"{_hm(b['jam'])} {b['cuaca']}" for b in bm["blok"][:4] if b["cuaca"])
                lines.append(f"[Resmi BMKG] {bm['area']}: {blok} (analisis {_date_hm(bm['as_of'])}).")

    if not lines:
        lines = ["Pertanyaan ini perlu AI untuk dijawab. Coba lagi beberapa menit lagi, sebut nama kota "
                 "(mis. \"cuaca Bogor\"), atau lihat angka terbaru di Dasbor dan Peta."]
    return AgentResult(answer="\n".join([NOTES[reason], *lines]), status="fallback", steps=steps, sources=sources,
                       checks=None, model=None, rounds=0, duration_ms=round((time.perf_counter() - t0) * 1000))
