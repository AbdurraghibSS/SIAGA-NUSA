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
3. Dua representasi per potongan, keduanya dihitung LOKAL (FastEmbed), tanpa kuota Gemini:
   - `dense`: `intfloat/multilingual-e5-small` (384 dimensi), menangkap makna/parafrasa;
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
EMBED_DIM = 384
EMBED_BATCH = 8
PREFETCH = 20
# BM25 FastEmbed tidak punya stemmer bahasa Indonesia, jadi stemming dimatikan dan stopword
# diganti daftar Indonesia (kata fungsi yang tidak membedakan topik).
ID_STOPWORDS = frozenset("""
ada adalah agar akan aku anda apa apabila atau bagai bagaimana bagi bahwa banyak beberapa belum
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

        if settings.embed_model not in {m["model"] for m in TextEmbedding.list_supported_models()}:
            TextEmbedding.add_custom_model(model=settings.embed_model, pooling=PoolingType.MEAN, normalization=True,
                                           sources=ModelSource(hf=settings.embed_model), dim=EMBED_DIM,
                                           model_file="onnx/model.onnx")
        _embedder = TextEmbedding(settings.embed_model, cache_dir=str(settings.data_dir / "models"), threads=2)
    return _embedder


def embed_texts(texts: list[str], task: str = "document") -> list[list[float]]:
    """Embedding lokal. Model e5 butuh awalan "passage: " untuk dokumen dan "query: " untuk pertanyaan."""
    prefix = "passage: " if task == "document" else "query: "
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

    m = _bm25()
    embs = m.embed(texts) if task == "document" else m.query_embed(texts)
    return [models.SparseVector(indices=e.indices.tolist(), values=e.values.tolist()) for e in embs]


def qdrant_client():
    from qdrant_client import QdrantClient

    from pipeline.config import settings

    return QdrantClient(url=settings.qdrant_url, timeout=5)


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

    qc = qdrant_client()
    name = settings.qdrant_collection
    if qc.collection_exists(name):
        qc.delete_collection(name)
    qc.create_collection(
        name,
        vectors_config={"dense": models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE)},
        sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    qc.create_payload_index(name, "doc", models.PayloadSchemaType.KEYWORD)
    qc.upsert(name, points=points, wait=True)
    summary["chunks"] = len(points)
    return summary


def search(query: str, k: int = 4, mode: str = "hybrid") -> list[dict]:
    """Potongan paling relevan untuk `query`. Dipakai tool agen `search_preparedness_guide`.

    mode: hybrid (default, RRF dense + BM25) | dense | bm25. Skor hybrid adalah skor RRF
    (urutan), bukan kemiripan kosinus."""
    from qdrant_client import models

    from pipeline.config import settings

    dense = models.Prefetch(query=embed_texts([query], task="query")[0], using="dense", limit=PREFETCH)
    sparse = models.Prefetch(query=sparse_texts([query], task="query")[0], using="bm25", limit=PREFETCH)
    qc = qdrant_client()
    if mode == "hybrid":
        res = qc.query_points(settings.qdrant_collection, prefetch=[dense, sparse],
                              query=models.FusionQuery(fusion=models.Fusion.RRF), limit=k, with_payload=True)
    else:
        pf = dense if mode == "dense" else sparse
        res = qc.query_points(settings.qdrant_collection, query=pf.query, using=pf.using, limit=k, with_payload=True)
    return [{"score": round(h.score, 3), **h.payload} for h in res.points]
