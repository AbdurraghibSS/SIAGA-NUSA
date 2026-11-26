"""BMKG Peringatan Dini Cuaca (nowcast) · RSS + dokumen CAP 1.2.

    RSS  https://www.bmkg.go.id/alerts/nowcast/id      daftar peringatan yang sedang aktif
    CAP  https://www.bmkg.go.id/alerts/nowcast/id/<kode>_alert.xml   satu peringatan

Setiap CAP berisi jenis kejadian (mis. "Hujan Lebat dan Petir"), masa berlaku
(`effective`–`expires`, biasanya 1–3 jam), tingkat CAP (urgency/severity/certainty),
daftar kecamatan di `description`, dan poligon wilayah. Nowcast BMKG TIDAK memakai
istilah Waspada/Siaga/Awas, jadi SIAGA NUSA menampilkan isinya apa adanya dan tidak
memetakan severity ke istilah status.

Catatan: `areaDesc` adalah wilayah kerja kantor BMKG, bukan batas administratif
("Jakarta" bisa berisi kecamatan di Tangerang). Kecocokan dengan kota pilot dihitung
dari poligon (PostGIS), bukan dari nama.

Server BMKG menolak User-Agent generik (403); sesi pipeline memakai UA SIAGA-NUSA.
Atribusi: wajib mencantumkan BMKG sebagai sumber.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime

RSS_URL = "https://www.bmkg.go.id/alerts/nowcast/id"
SOURCE = "bmkg-alert"
_CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
_PLACES = re.compile(r"khususnya di (.+?)(?:\.\s|\.$|\n)", re.IGNORECASE | re.DOTALL)


def parse_rss(xml_text: str) -> list[dict]:
    """RSS → [{title, link, guid, pub_date}] untuk setiap peringatan aktif."""
    root = ET.fromstring(xml_text)
    return [{"title": (it.findtext("title") or "").strip(), "link": (it.findtext("link") or "").strip(),
             "guid": (it.findtext("guid") or "").strip(), "pub_date": it.findtext("pubDate")}
            for it in root.findall("./channel/item")]


def province_from_title(title: str) -> str | None:
    """'Hujan Lebat disertai Petir di Jawa Timur' → 'Jawa Timur'."""
    m = re.search(r"\bdi\s+(.+)$", title or "")
    return m.group(1).strip() if m else None


def places_from_description(desc: str) -> list[str]:
    """Daftar kecamatan setelah 'khususnya di', ditulis BMKG dalam huruf kapital."""
    m = _PLACES.search(desc or "")
    if not m:
        return []
    raw = re.sub(r"\s+dan\s+", ", ", m.group(1))
    return [p.strip().title() for p in raw.split(",") if p.strip()]


def polygon_wkt(cap_polygon: str) -> str | None:
    """CAP 'lat,lon lat,lon ...' → WKT 'POLYGON((lon lat, ...))' (ditutup kalau belum)."""
    pts = []
    for pair in (cap_polygon or "").split():
        lat, _, lon = pair.partition(",")
        try:
            pts.append((float(lon), float(lat)))
        except ValueError:
            continue
    if len(pts) < 3:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    if len(pts) < 4:
        return None
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in pts) + "))"


def parse_cap(xml_text: str, cap_url: str) -> dict:
    """Satu dokumen CAP → satu baris `weather_alerts` (geometri sebagai WKT MultiPolygon)."""
    root = ET.fromstring(xml_text)
    g = lambda el, tag: (el.findtext(_CAP + tag) or "").strip() or None  # noqa: E731
    info = root.find(_CAP + "info")
    if info is None:
        raise ValueError("CAP tanpa elemen <info>")
    area = info.find(_CAP + "area")
    polys = [w for p in (area.findall(_CAP + "polygon") if area is not None else []) if (w := polygon_wkt(p.text))]
    desc = g(info, "description") or ""
    headline = g(info, "headline") or ""
    return {
        "identifier": g(root, "identifier"),
        "msg_type": g(root, "msgType"),
        "sent_at": datetime.fromisoformat(g(root, "sent")),
        "effective_at": datetime.fromisoformat(g(info, "effective") or g(root, "sent")),
        "expires_at": datetime.fromisoformat(g(info, "expires")),
        "event": g(info, "event"),
        "urgency": g(info, "urgency"),
        "severity": g(info, "severity"),
        "certainty": g(info, "certainty"),
        "headline": headline,
        "description": desc,
        "area_desc": g(area, "areaDesc") if area is not None else None,
        "province": province_from_title(headline),
        "places": places_from_description(desc),
        "infographic_url": g(info, "web"),
        "cap_url": cap_url,
        "geom_wkt": ("MULTIPOLYGON(" + ", ".join(w[len("POLYGON"):] for w in polys) + ")") if polys else None,
    }
