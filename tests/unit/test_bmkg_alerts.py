"""Parser peringatan dini BMKG (RSS + CAP 1.2), tanpa jaringan."""

import pytest

from pipeline.ingest import bmkg_alerts as ba

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Peringatan Dini Cuaca BMKG</title>
<item><title>Hujan Lebat disertai Petir di DI Yogyakarta</title>
<link>https://www.bmkg.go.id/alerts/nowcast/id/CYG20261126003_alert.xml</link>
<guid>2.49.0.1.360.0.2026.11.26.08.34.003</guid><pubDate>Thu, 26 Nov 2026 14:54:00 +0700</pubDate></item>
</channel></rss>"""

CAP = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>2.49.0.1.360.0.2026.11.26.08.34.003</identifier><sent>2026-11-26T14:54:00+07:00</sent>
  <status>Actual</status><msgType>Alert</msgType><scope>Public</scope>
  <info><language>id</language><category>Met</category><event>Hujan Lebat dan Petir</event>
    <urgency>Immediate</urgency><severity>Moderate</severity><certainty>Observed</certainty>
    <effective>2026-11-26T15:00:00+07:00</effective><expires>2026-11-26T17:00:00+07:00</expires>
    <headline>Hujan Lebat disertai Petir di DI Yogyakarta</headline>
    <description>Hujan lebat disertai petir akan terjadi pada 26 November 2026, 15:00 WIB di sebagian wilayah DI Yogyakarta, khususnya di BANGUNTAPAN, BERBAH, DEPOK dan KALASAN.
 Kondisi ini berpotensi menimbulkan dampak berupa genangan.</description>
    <web>https://nowcasting.bmkg.go.id/infografis/CYG/2026/11/26/infografis.jpg</web>
    <area><areaDesc>DI Yogyakarta</areaDesc>
      <polygon>-7.80,110.40 -7.80,110.45 -7.75,110.45 -7.75,110.40</polygon>
      <polygon>rusak</polygon>
    </area></info></alert>"""


def test_parse_rss_items():
    [item] = ba.parse_rss(RSS)
    assert item["guid"].endswith("34.003") and item["link"].endswith("_alert.xml")


def test_parse_cap_fields_places_and_geometry():
    r = ba.parse_cap(CAP, "https://x/cap.xml")
    assert r["event"] == "Hujan Lebat dan Petir" and r["severity"] == "Moderate"
    assert r["effective_at"].hour == 15 and r["expires_at"].hour == 17
    assert r["province"] == "DI Yogyakarta"
    assert r["places"] == ["Banguntapan", "Berbah", "Depok", "Kalasan"]
    assert r["geom_wkt"] == "MULTIPOLYGON(((110.4 -7.8, 110.45 -7.8, 110.45 -7.75, 110.4 -7.75, 110.4 -7.8)))"


@pytest.mark.parametrize("raw, ok", [("-6.1,106.8 -6.2,106.8 -6.2,106.9", True), ("-6.1,106.8 -6.2,106.8", False), ("", False)])
def test_polygon_wkt_closes_ring_and_rejects_degenerate(raw, ok):
    wkt = ba.polygon_wkt(raw)
    assert (wkt is not None) == ok
    if ok:
        assert wkt.startswith("POLYGON((106.8 -6.1") and wkt.endswith("106.8 -6.1))")


def test_cap_without_info_is_rejected():
    with pytest.raises(ValueError):
        ba.parse_cap('<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>x</identifier></alert>', "u")
