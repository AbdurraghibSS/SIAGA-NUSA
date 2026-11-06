import json

import pandas as pd

from pipeline.clean import petabencana as pb


def _feature(pkey, created_at, text="", lon=106.83, lat=-6.20, region="3171", partner=None, image=True, kind="flood"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "pkey": str(pkey), "created_at": created_at, "source": "grasp", "status": "confirmed",
            "disaster_type": kind, "report_data": {"report_type": kind, "flood_depth": 50},
            "text": text, "partner_code": partner, "image_url": "x.jpg" if image else None,
            "tags": {"district_id": None, "region_code": region, "local_area_id": None, "instance_region_code": "ID-JK"},
        },
    }


def _frame(tmp_path, features, name="archive_2024-01.json"):
    (tmp_path / name).write_text(json.dumps({"features": features}))
    return pb.load_archive(tmp_path)


def test_load_archive_flattens_and_dedupes(tmp_path):
    f = _feature(1, "2024-01-01T03:00:00Z")
    (tmp_path / "archive_2023-12.json").write_text(json.dumps({"features": [f]}))
    df = _frame(tmp_path, [f, _feature(2, "2024-01-02T03:00:00Z")])
    assert sorted(df.pkey) == ["1", "2"]
    assert str(df.created_at_wib.dt.tz) == "Asia/Jakarta"


def test_drill_and_test_texts_are_flagged():
    df = pd.DataFrame({"text": [
        "#HKB annur", "Duta_sukaedah", "#112challenge_bpbdsleman", "tes", "Test: Very big flood",
        "simulasi banjir", "Banjir 50 cm di depan rumah", "Siaga 1 kali angke hulu",
        "SDN 07 Duren Sawit mulai tergenang", "banjir 30 sd 50 cm", None,
    ]})
    assert pb.flag_drill_text(df).tolist() == [True] * 6 + [False] * 5


def test_test_partner_flag():
    df = pd.DataFrame({"partner_code": ["tescode", "TESCODE", "bpbd2022", None]})
    assert pb.flag_test_partner(df).tolist() == [True, True, False, False]


def test_jabodetabek_by_region_code_or_bbox():
    df = pd.DataFrame({
        "region_code": ["3171", "3202", None, None],  # Jaksel, Sukabumi, tanpa kode (Jakarta), tanpa kode (Bandung)
        "lon": [106.8, 106.9, 106.8, 107.6],
        "lat": [-6.25, -6.9, -6.2, -6.9],
    })
    assert pb.in_jabodetabek(df).tolist() == [True, False, True, False]


def test_burst_flags_drill_like_clusters_but_not_real_flood_volume(tmp_path):
    feats = [_feature(i, "2024-11-13T06:10:00Z", image=False) for i in range(12)]  # 12 laporan, tanpa foto
    feats += [_feature(100 + i, "2020-02-25T01:10:00Z", lon=106.90, image=True) for i in range(18)]  # banjir nyata
    feats += [_feature(200 + i, "2024-05-22T07:05:00Z", lon=106.70, image=True) for i in range(30)]  # kelas, berfoto
    df = _frame(tmp_path, feats)
    burst = pb.flag_burst(df)
    assert burst[df.pkey.astype(int) < 100].all()
    assert not burst[df.pkey.astype(int).between(100, 199)].any()
    assert burst[df.pkey.astype(int) >= 200].all()


def test_clean_floods_marks_exclusions_and_keeps_only_floods(tmp_path):
    df = _frame(tmp_path, [
        _feature(1, "2024-01-01T03:00:00Z", "banjir sepinggang"),
        _feature(2, "2024-01-01T03:00:00Z", "hkb annur"),
        _feature(3, "2024-01-01T03:00:00Z", partner="tescode"),
        _feature(4, "2024-01-01T03:00:00Z", kind="wind"),
        _feature(5, "2024-01-01T03:00:00Z", region="3273", lon=107.6, lat=-6.9),  # Bandung
    ])
    out = pb.clean_floods(df)
    assert sorted(out.pkey) == ["1", "2", "3"]
    assert out.set_index("pkey").is_excluded.to_dict() == {"1": False, "2": True, "3": True}


def test_rainy_season_labels():
    ts = pd.Series(pd.to_datetime(["2023-11-01", "2024-04-30", "2024-05-01", "2024-10-31", "2024-12-15"]))
    assert pb.rainy_season(ts).tolist() == [2023, 2023, pd.NA, pd.NA, 2024]
