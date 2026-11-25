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
    "quota": "Mode hemat: kuota AI sedang habis, jadi jawaban ini disusun otomatis dari data tanpa AI.",
    "off": "Mode hemat: AI belum diaktifkan di server ini, jadi jawaban ini disusun otomatis dari data tanpa AI.",
}

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


def _hm(iso: str | None) -> str:
    """'2026-11-26T04:00:00+07:00' → '04.00' (format jam Indonesia)."""
    return (iso or "")[11:16].replace(":", ".")


def _mm(x) -> str:
    return "–" if x is None else f"{x:.1f}".replace(".", ",")


def answer(question: str, reason: str = "quota") -> AgentResult:
    t0 = time.perf_counter()
    steps: list[Step] = []
    sources: list[dict] = []
    city = _find_city(question)
    lines: list[str] = []

    if _GUIDE.search(question) and not (city and _RAIN.search(question) and not _RISK.search(question)):
        res = _call(steps, "search_preparedness_guide", {"query": question})
        if res.get("ok") and res.get("potongan"):
            lines.append("Kutipan panduan resmi yang paling relevan:")
            for p in res["potongan"][:2]:
                th = f" {p['tahun']}" if p.get("tahun") else ""
                lines.append(f"- [Panduan resmi] {p['teks'][:450].rstrip()}… ({p['penerbit']}{th}, hlm. {p['halaman']})")
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
                             f"sekitar pukul {_hm(om['puncak_jam'])}.")
            bm = res.get("bmkg_per_3_jam")
            if bm:
                blok = ", ".join(f"{_hm(b['jam'])} {b['cuaca']}" for b in bm["blok"][:4] if b["cuaca"])
                lines.append(f"[Resmi BMKG] {bm['area']}: {blok}.")

    if not lines:
        lines = ["Pertanyaan ini perlu AI untuk dijawab. Coba lagi beberapa menit lagi, sebut nama kota "
                 "(mis. \"cuaca Bogor\"), atau lihat angka terbaru di Dasbor dan Peta."]
    return AgentResult(answer="\n".join([NOTES[reason], *lines]), status="fallback", steps=steps, sources=sources,
                       checks=None, model=None, rounds=0, duration_ms=round((time.perf_counter() - t0) * 1000))
