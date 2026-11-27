"""RAG · PDF panduan kesiapsiagaan → potongan teks → embedding lokal (e5) → vector DB Qdrant.

    docker compose up -d qdrant
    python -m pipeline.run knowledge

PDF tidak di-commit (hak cipta penerbit). Unduh dari URL di `SOURCES` (semuanya domain .go.id),
taruh di `docs/` dengan nama file yang sama, lalu jalankan job ini. Koleksi dibangun ulang dari nol setiap
kali, jadi aman dijalankan lagi setelah menambah PDF atau mengganti model embedding.

Langkah:
1. Ekstrak teks per halaman (pypdf). Buang baris isian ("____") dan baris yang hanya angka
   (nomor halaman, daftar isi).
2. Potong per kata lintas halaman: jendela `WINDOW` kata, geser `STEP` kata (tumpang tindih
   `WINDOW − STEP`), supaya kalimat di batas halaman tidak terputus. Setiap potongan
   menyimpan rentang halaman untuk sitasi.
3. Dua representasi per potongan, tanpa kuota Gemini. Dihitung LOKAL (FastEmbed) atau, kalau
   QDRANT_CLOUD_INFERENCE=true, oleh server Qdrant Cloud dengan model yang sama (gratis):
   - `dense`: EMBED_MODEL di .env (default `intfloat/multilingual-e5-small`, 384 dimensi),
     menangkap makna/parafrasa;
   - `bm25`:  vektor sparse kata kunci, IDF dihitung Qdrant. Menangkap istilah persis yang
     sering meleset di dense (leptospirosis, waspada/siaga/awas, tas siaga).
4. Pencarian hybrid: ambil 20 teratas dari masing-masing, gabungkan dengan Reciprocal Rank
   Fusion (RRF) di Qdrant. Payload menyimpan teks + judul + penerbit + halaman untuk sitasi.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

WINDOW = 200
STEP = 160
MIN_WORDS = 40          # sisa terakhir yang lebih pendek digabung ke potongan sebelumnya
EMBED_BATCH = 8
PREFETCH = 20
# BM25 FastEmbed tidak punya stemmer bahasa Indonesia, jadi stemming dimatikan dan stopword
# diganti daftar Indonesia (kata fungsi yang tidak membedakan topik).
ID_STOPWORDS = frozenset("""
ada adalah agar apa dua tiga pun pak bu akan aku anda apa apabila atau bagai bagaimana bagi bahwa banyak beberapa belum
benar berupa bila bisa boleh dalam dan dapat dari daripada demikian dengan di dia dimana harus hal
hanya hingga ia ialah ini itu jadi jika juga kalau kami kamu karena ke kepada ketika kita lagi lain
lalu maka mana masih mau melalui mereka misalnya mungkin nya oleh pada para per perlu saat saja sama
sambil sang sangat saya sebagai sebelum sedang sehingga sejak sekitar selain selama seperti serta
setelah setiap suatu sudah supaya tak tanpa telah tentang tersebut tetapi tidak untuk yaitu yakni yang
""".split())
_NS = uuid.UUID("6f1c0a52-5b8e-4f43-9a51-5ec1a6a7a001")  # namespace id titik Qdrant


@dataclass(frozen=True)
class Source:
    doc: str
    file: str
    title: str
    publisher: str
    year: int | None      # None = tahun tidak tercetak di dokumen (jangan ditebak dari metadata PDF)
    url: str | None = None


SOURCES: tuple[Source, ...] = (
    # Panduan untuk masyarakat
    Source("bnpb-buku-saku", "6-buku-saku-cetakan-4-2019.pdf",
           "Buku Saku Tanggap Tangkas Tangguh Menghadapi Bencana (cetakan ke-4)", "BNPB", 2019),
    Source("bpbd-dki-banjir", "buku-saku-panduan-kesiapsiagaan-menghadapi-banjir-bagi-masyarakat.pdf",
           "Panduan Kesiapsiagaan Menghadapi Banjir bagi Masyarakat", "BPBD Provinsi DKI Jakarta", 2020),
    Source("bnpb-keluarga", "bnpb-panduan-kesiapsiagaan-keluarga.pdf",
           "Panduan Kesiapsiagaan Bencana untuk Keluarga", "BNPB", 2018,
           "https://ppid.demakkab.go.id/asset/files/dokumendokumen/d1e6343258a5d7b07a20a3760c0d2027.pdf"),
    Source("bnpb-cuaca-ekstrem", "bnpb-panduan-edukasi-cuaca-ekstrem.pdf",
           "Panduan Edukasi Bencana Cuaca Ekstrem", "BNPB (Pusdiklat PB)", None,
           "https://ppid.demakkab.go.id/asset/files/dokumendokumen/8c3d8275e70251e616e6b56a39e922f1.pdf"),
    Source("bpbd-dki-latihan", "bpbd-dki-modul-latihan-banjir-longsor.pdf",
           "Modul Lanjutan Latihan Kesiapsiagaan Menghadapi Bencana Banjir dan Gerakan Tanah/Longsor di Provinsi DKI Jakarta",
           "BPBD Provinsi DKI Jakarta", None,
           "https://bpbd.jakarta.go.id/data/files/perpustakaan/2026/07/16/333/178417200710-modul-lanjutan-latihan-"
           "kesiapsiagaan-menghadapi-bencana-banjir-dan-gerakan-tanah-longsor-di-provinsi-dki-jakarta.pdf"),
    Source("esdm-gerakan-tanah", "esdm-pengenalan-gerakan-tanah.pdf",
           "Pengenalan Gerakan Tanah", "Kementerian ESDM", None,
           "https://www.esdm.go.id/assets/media/content/Pengenalan_Gerakan_Tanah.pdf"),
    Source("bnpb-karakteristik", "bnpb-karakteristik-bencana-mitigasi.pdf",
           "Pengenalan Karakteristik Bencana dan Upaya Mitigasinya di Indonesia (Edisi II)", "BAKORNAS PB (kini BNPB)", 2007,
           "https://www.bnpb.go.id/storage/app/media/uploads/migration/pubs/470.pdf"),
    # Definisi resmi dan pedoman petugas (bahasanya lebih teknis)
    Source("bmkg-istilah-prakiraan", "bmkg-istilah-simbol-prakiraan-cuaca.pdf",
           "SE Deputi Meteorologi No. SE.3/DM/XII/2024: Jenis dan Simbol Parameter Prakiraan Cuaca", "BMKG", 2024,
           "https://jdih.bmkg.go.id/common/dokumen/2024sedmbmkg003.pdf"),
    Source("bmkg-peringatan-dini", "bmkg-peringatan-dini-cuaca-ekstrem.pdf",
           "Peraturan BMKG No. 9 Tahun 2022 tentang Peringatan Dini Cuaca Ekstrem", "BMKG", 2022,
           "https://jdih.bmkg.go.id/common/dokumen/perbanno.9tahun2022.pdf"),
    Source("kemenkes-krisis-kesehatan", "kemenkes-buku-saku-krisis-kesehatan.pdf",
           "Buku Saku Petugas Lapangan Penanggulangan Krisis Kesehatan", "Kementerian Kesehatan", 2014,
           "https://pusatkrisis.kemkes.go.id/__pub/files59107Buku%20Saku%20PPKK%202014_Final.pdf"),
)

_JUNK_LINE = re.compile(r"^[\W\d_]*$|_{4,}")  # hanya angka/tanda baca, atau garis isian


def clean_page(raw: str) -> list[str]:
    """Teks satu halaman → daftar kata, tanpa baris isian/nomor."""
    words: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or _JUNK_LINE.search(line):
            continue
        words.extend(line.replace("­", "").split())
    return words


def chunk_pages(pages: list[list[str]], window: int = WINDOW, step: int = STEP) -> list[dict]:
    """Jendela geser per kata lintas halaman. `pages[i]` = kata di halaman i+1.

    Kembalikan [{page, page_end, text}], halaman mulai dari 1."""
    stream = [(w, i + 1) for i, words in enumerate(pages) for w in words]
    chunks = []
    start = 0
    while start < len(stream):
        end = min(start + window, len(stream))
        if len(stream) - end < MIN_WORDS:  # sisa pendek ikut potongan ini
            end = len(stream)
        part = stream[start:end]
        chunks.append({"page": part[0][1], "page_end": part[-1][1], "text": " ".join(w for w, _ in part)})
        if end == len(stream):
            break
        start += step
    return chunks


def read_pdf(path: Path) -> list[list[str]]:
    from pypdf import PdfReader

    return [clean_page(p.extract_text() or "") for p in PdfReader(path).pages]


def point_id(doc: str, n: int) -> str:
    """Id stabil per potongan (Qdrant butuh UUID atau bilangan bulat)."""
    return str(uuid.uuid5(_NS, f"{doc}:{n}"))


# ---------------------------------------------------------------------------
# Embedding & Qdrant
# ---------------------------------------------------------------------------
_embedder = None


def _model():
    """Model embedding lokal (FastEmbed/ONNX, tanpa PyTorch), dimuat sekali per proses.

    multilingual-e5-small: 384 dimensi, 512 token, dilatih untuk retrieval ±100 bahasa
    termasuk Indonesia. all-MiniLM-L6-v2 hanya Inggris; paraphrase-multilingual-MiniLM
    hanya membaca 128 token pertama, terlalu pendek untuk potongan 200 kata.
    File model (±470 MB) disimpan di data/models, diunduh sekali dari Hugging Face."""
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType

        from pipeline.config import settings

        known = {m["model"]: m.get("dim") for m in TextEmbedding.list_supported_models()}
        if settings.embed_model in known:
            if known[settings.embed_model] and known[settings.embed_model] != settings.embed_dim:
                raise ValueError(f"EMBED_DIM={settings.embed_dim}, padahal {settings.embed_model} "
                                 f"berdimensi {known[settings.embed_model]}. Sesuaikan EMBED_DIM di .env.")
        else:
            # Model di luar daftar FastEmbed: dianggap ONNX di onnx/model.onnx dengan mean pooling (gaya e5).
            TextEmbedding.add_custom_model(model=settings.embed_model, pooling=PoolingType.MEAN, normalization=True,
                                           sources=ModelSource(hf=settings.embed_model), dim=settings.embed_dim,
                                           model_file="onnx/model.onnx")
        _embedder = TextEmbedding(settings.embed_model, cache_dir=str(settings.data_dir / "models"), threads=2)
    return _embedder


BM25_MODEL = "qdrant/bm25"
# BM25 di server Qdrant: stemmer bahasa Inggris dimatikan ("none"). Daftar stopword kustom ditolak
# server (400), jadi kata umum Indonesia ditangani bobot IDF koleksi.
BM25_CLOUD_OPTIONS = {"language": "none"}


def _cloud() -> bool:
    from pipeline.config import settings

    return settings.qdrant_cloud_inference


def embed_prefix(task: str) -> str:
    """Awalan teks untuk model dense: dari EMBED_QUERY_PREFIX/EMBED_DOC_PREFIX, atau otomatis
    ("query: "/"passage: " untuk keluarga e5, kosong untuk model lain)."""
    from pipeline.config import settings

    explicit = settings.embed_doc_prefix if task == "document" else settings.embed_query_prefix
    if explicit is not None:
        return explicit
    if "e5" in settings.embed_model.lower():
        return "passage: " if task == "document" else "query: "
    return ""


def embed_texts(texts: list[str], task: str = "document") -> list:
    """Vektor dense untuk dokumen (`task="document"`) atau pertanyaan (`task="query"`).

    Mode Cloud Inference: kembalikan `Document` (teks + nama model) yang di-embed server Qdrant."""
    prefix = embed_prefix(task)
    if _cloud():
        from qdrant_client import models

        from pipeline.config import settings

        return [models.Document(text=prefix + t, model=settings.embed_model) for t in texts]
    # Batch kecil: puncak memori ONNX naik kuadratik dengan panjang token × batch. Batch 32 pernah
    # membuat proses dimatikan OOM di laptop 14 GB yang menjalankan beberapa stack Docker.
    return [v.tolist() for v in _model().embed([prefix + t for t in texts], batch_size=EMBED_BATCH)]


_sparse = None


def _bm25():
    global _sparse
    if _sparse is None:
        from fastembed import SparseTextEmbedding

        from pipeline.config import settings

        _sparse = SparseTextEmbedding("Qdrant/bm25", cache_dir=str(settings.data_dir / "models"),
                                      disable_stemmer=True, stopwords=set(ID_STOPWORDS))
    return _sparse


def sparse_texts(texts: list[str], task: str = "document"):
    """Vektor BM25 (indices, values). Untuk kueri, bobot tiap kata = 1 (IDF dari Qdrant)."""
    from qdrant_client import models

    if _cloud():
        return [models.Document(text=t, model=BM25_MODEL, options=BM25_CLOUD_OPTIONS) for t in texts]

    m = _bm25()
    embs = m.embed(texts) if task == "document" else m.query_embed(texts)
    return [models.SparseVector(indices=e.indices.tolist(), values=e.values.tolist()) for e in embs]


def qdrant_client():
    from qdrant_client import QdrantClient

    from pipeline.config import settings

    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key,
                        timeout=30 if settings.qdrant_cloud_inference else 5,
                        cloud_inference=settings.qdrant_cloud_inference)


def build(knowledge_dir: Path) -> dict:
    """Bangun ulang koleksi dari semua PDF yang ada. Kembalikan ringkasan untuk log job."""
    from qdrant_client import models

    from pipeline.config import settings

    points, summary = [], {"docs": [], "missing": []}
    for src in SOURCES:
        path = knowledge_dir / src.file
        if not path.exists():
            summary["missing"].append(src.file)
            log.warning("PDF %s tidak ada di %s, dilewati", src.file, knowledge_dir)
            continue
        chunks = chunk_pages(read_pdf(path))
        texts = [c["text"] for c in chunks]
        vectors = zip(embed_texts(texts), sparse_texts(texts))
        points += [models.PointStruct(id=point_id(src.doc, n), vector={"dense": d, "bm25": sp}, payload={
            "doc": src.doc, "title": src.title, "publisher": src.publisher, "year": src.year, "url": src.url,
            "page": c["page"], "page_end": c["page_end"], "text": c["text"],
        }) for n, (c, (d, sp)) in enumerate(zip(chunks, vectors))]
        summary["docs"].append(f"{src.doc} ({len(chunks)})")
        log.info("%s: %d potongan", src.doc, len(chunks))
    if not points:
        raise RuntimeError(f"Tidak ada PDF sumber di {knowledge_dir}")

    write_doc_freq([p.payload["text"] for p in points], settings.data_dir / DF_FILE)

    qc = qdrant_client()
    name = settings.qdrant_collection
    if qc.collection_exists(name):
        qc.delete_collection(name)
    qc.create_collection(
        name,
        vectors_config={"dense": models.VectorParams(size=settings.embed_dim, distance=models.Distance.COSINE)},
        sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    qc.create_payload_index(name, "doc", models.PayloadSchemaType.KEYWORD)
    # Per batch: di mode cloud, setiap batch juga di-embed server (batas ukuran permintaan).
    for i in range(0, len(points), 32):
        qc.upsert(name, points=points[i:i + 32], wait=True)
    summary["chunks"] = len(points)
    return summary


DF_FILE = "knowledge_df.json"
_WORD = re.compile(r"[a-z]{3,}")  # 3 huruf: "tas", "air" bermakna; kata fungsi dibuang lewat stopword


def words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower())) - ID_STOPWORDS


def write_doc_freq(texts: list[str], path: Path) -> None:
    """Frekuensi dokumen tiap kata di seluruh korpus, untuk bobot IDF di mode hemat (tanpa LLM).

    Ditulis ke tabel `knowledge_df` (dibaca API, termasuk di Vercel) dan ke file JSON lokal."""
    import json
    from collections import Counter

    from sqlalchemy import text

    from pipeline import db

    df = Counter(w for t in texts for w in words(t))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"n": len(texts), "df": df}, ensure_ascii=False), encoding="utf-8")
    rows = [{"w": w, "d": d} for w, d in df.items()] + [{"w": N_KEY, "d": len(texts)}]
    with db.engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS knowledge_df (word TEXT PRIMARY KEY, df INTEGER NOT NULL)"))
        conn.execute(text("TRUNCATE knowledge_df"))
        conn.execute(text("INSERT INTO knowledge_df (word, df) VALUES (:w, :d)"), rows)


N_KEY = "__n__"  # tidak mungkin bentrok: kata korpus hanya huruf kecil a–z
_df_cache: dict | None = None


def _load_df() -> dict:
    """Dari tabel knowledge_df; kalau kosong/gagal, dari file lokal; kalau tidak ada, kosong."""
    import json

    from sqlalchemy import text

    from pipeline.config import settings

    try:
        from pipeline import db

        with db.engine.connect() as conn:
            rows = dict(conn.execute(text("SELECT word, df FROM knowledge_df")).all())
        if rows:
            return {"n": rows.pop(N_KEY, 0), "df": rows}
    except Exception:  # tabel belum ada / DB tidak terjangkau: pakai cadangan
        log.debug("knowledge_df tidak terbaca dari DB", exc_info=True)
    path = settings.data_dir / DF_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"n": 0, "df": {}}


def idf(word: str) -> float:
    """log((N+1)/(df+1)) dari korpus; kata yang tidak ada di korpus = 0 (tidak membantu memilih)."""
    import math

    global _df_cache
    if _df_cache is None:
        _df_cache = _load_df()
    df = _df_cache["df"].get(word, 0)
    return math.log((_df_cache["n"] + 1) / (df + 1)) if df else 0.0


def search(query: str, k: int = 4, mode: str = "hybrid") -> list[dict]:
    """Potongan paling relevan untuk `query`. Dipakai tool agen `search_preparedness_guide`.

    mode: hybrid (default, RRF dense + BM25) | dense | bm25. Skor hybrid adalah skor RRF
    (urutan), bukan kemiripan kosinus."""
    from qdrant_client import models

    from pipeline.config import settings

    dense = models.Prefetch(query=embed_texts([query], task="query")[0], using="dense", limit=PREFETCH)
    sparse = models.Prefetch(query=sparse_texts([query], task="query")[0], using="bm25", limit=PREFETCH)
    qc = qdrant_client()
    try:
        if mode == "hybrid":
            res = qc.query_points(settings.qdrant_collection, prefetch=[dense, sparse],
                                  query=models.FusionQuery(fusion=models.Fusion.RRF), limit=k, with_payload=True)
        else:
            pf = dense if mode == "dense" else sparse
            res = qc.query_points(settings.qdrant_collection, query=pf.query, using=pf.using, limit=k,
                                  with_payload=True)
    except Exception as exc:
        if "dimension" in str(exc).lower():  # EMBED_MODEL diganti tapi koleksi belum dibangun ulang
            raise RuntimeError(f"Koleksi {settings.qdrant_collection} dibangun dengan model embedding lain "
                               f"(EMBED_MODEL={settings.embed_model}, EMBED_DIM={settings.embed_dim}). "
                               "Jalankan: python -m pipeline.run knowledge") from exc
        raise
    return [{"score": round(h.score, 3), **h.payload} for h in res.points]
