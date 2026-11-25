"""Penjaga agen (plan §7.4–7.5) · kode Python biasa, tanpa LLM.

Dua titik:
1. `check_input`  sebelum Gemini dipanggil: panjang dan pola prompt injection yang umum.
   Ini lapis pertama saja; lapis berikutnya adalah system prompt, tool read-only, dan
   teks warga yang dibungkus <data_warga>.
2. `check_answer` setelah Gemini menjawab: setiap angka di jawaban harus bisa ditemukan di
   hasil tool (atau di pertanyaan), dan istilah status resmi (Waspada/Siaga/Awas) tidak boleh
   dinyatakan sendiri. Hasilnya ditampilkan di UI, bukan menghapus jawaban.
"""

import json
import re
from dataclasses import dataclass, field

MAX_QUESTION = 500

_INJECTION = [
    r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|above|prior|all)\b.{0,20}\b(instructions?|rules?|prompts?)\b",
    r"\b(abaikan|lupakan|acuhkan)\b.{0,40}\b(instruksi|perintah|aturan|prompt)\b",
    r"\b(system|developer)\s*(prompt|message|instructions?)\b",
    r"\b(prompt|instruksi)\s+(sistem|awal|rahasia)\b",
    r"\b(tampilkan|bocorkan|tunjukkan|reveal|print|show)\b.{0,30}\b(prompt|instruksi|api[\s_-]?key|kunci)\b",
    r"\b(jailbreak|DAN mode|developer mode|mode pengembang)\b",
    r"\b(you are now|kamu sekarang adalah|anggap dirimu|berperanlah sebagai|act as)\b",
    r"</?\s*(system|data_warga|tool)\s*>",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION]

# Istilah status peringatan resmi. Boleh muncul hanya bila menyebut bahwa status itu
# wewenang BMKG/BPBD; agen sendiri tidak boleh menetapkannya.
_STATUS_RE = re.compile(r"\b(status|level|siaga)\s+(waspada|siaga|awas)\b|\b(siaga\s+[1-4I]{1,3})\b", re.IGNORECASE)
_OFFICIAL_CONTEXT = re.compile(r"\b(BMKG|BPBD|BNPB|resmi|pemerintah)\b", re.IGNORECASE)

_MONTHS = "januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember|jan|feb|mar|apr|jun|jul|agu|agt|sep|okt|nov|des"
_SKIP_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}(T[\d:+.-]+)?\b"),                          # tanggal ISO
    re.compile(rf"\b\d{{1,2}}\s+({_MONTHS})\b(\s+\d{{4}})?", re.IGNORECASE),    # 25 November 2026
    re.compile(r"\b(pukul|jam|pkl\.?)\s*\d{1,2}([.:]\d{2})?(\s*[–-]\s*\d{1,2}([.:]\d{2})?)?", re.IGNORECASE),
    re.compile(r"\b\d{1,2}[.:]\d{2}(\s*[–-]\s*\d{1,2}[.:]\d{2})?\s*(WIB|WITA|WIT)?\b"),  # 15.00–18.00 WIB
    re.compile(r"\b(19|20)\d{2}\b"),                                              # tahun
    re.compile(r"\b(hlm|halaman|hal)\.?\s*\d+(\s*[–-]\s*\d+)?", re.IGNORECASE),  # sitasi halaman
    re.compile(r"\b112\b|\b11[0-9]\b"),                                           # nomor darurat
]
_NUMBER = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*(?:[.,]\d+)?")
# Angka kecil dan ambang tetap yang wajar muncul tanpa harus ada di hasil tool.
_FREE = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 20, 24, 35, 48, 50, 72, 100, 150}


@dataclass
class InputCheck:
    ok: bool
    reason: str | None = None
    message: str | None = None


@dataclass
class AnswerCheck:
    numbers_ok: bool = True
    unsupported_numbers: list[str] = field(default_factory=list)
    status_terms: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"numbers_ok": self.numbers_ok, "unsupported_numbers": self.unsupported_numbers,
                "status_terms": self.status_terms}


def check_input(question: str) -> InputCheck:
    q = (question or "").strip()
    if not q:
        return InputCheck(False, "empty", "Pertanyaannya kosong.")
    if len(q) > MAX_QUESTION:
        return InputCheck(False, "too_long", f"Pertanyaan terlalu panjang (maks {MAX_QUESTION} karakter).")
    for rx in _INJECTION_RE:
        if rx.search(q):
            return InputCheck(False, "injection",
                              "Saya hanya bisa membantu soal cuaca, hujan, dan banjir dari data SIAGA NUSA. "
                              "Instruksi untuk mengubah aturan saya tidak bisa saya ikuti.")
    return InputCheck(True)


def parse_number(token: str) -> float | None:
    """'12,4' → 12.4 · '1.250' → 1250 · '1.250,5' → 1250.5 · '0.43' → 0.43."""
    t = token
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".") if t.count(",") == 1 else t.replace(",", "")
    elif t.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def _collect(obj, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        if 0 < obj < 1:  # peluang 0.43 → 43 %
            out.add(round(obj * 100, 1))
    elif isinstance(obj, str):
        for tok in _NUMBER.findall(obj):
            v = parse_number(tok)
            if v is not None:
                out.add(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, out)


def _matches(value: float, token: str, known: set[float]) -> bool:
    decimals = len(re.split(r"[.,]", token)[-1]) if re.search(r"[.,]\d{1,2}$", token) else 0
    tol = 0.5 if decimals == 0 else 0.05 if decimals == 1 else 0.005
    return any(abs(value - k) <= tol + 1e-9 for k in known)


def check_answer(answer: str, tool_results: list[dict], question: str = "") -> AnswerCheck:
    text = answer or ""
    for rx in _SKIP_PATTERNS:
        text = rx.sub(" ", text)
    known: set[float] = set()
    _collect(tool_results, known)
    _collect(question, known)
    unsupported = []
    for tok in _NUMBER.findall(text):
        v = parse_number(tok)
        if v is None or v in _FREE or _matches(v, tok, known):
            continue
        unsupported.append(tok)
    status = []
    for m in _STATUS_RE.finditer(answer or ""):
        around = (answer or "")[max(0, m.start() - 80): m.end() + 80]
        if not _OFFICIAL_CONTEXT.search(around):
            status.append(m.group(0))
    return AnswerCheck(numbers_ok=not unsupported, unsupported_numbers=sorted(set(unsupported)), status_terms=status)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
