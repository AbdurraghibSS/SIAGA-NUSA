import pytest

from pipeline.rainfall import MODEL_A_THRESHOLD_MM, bmkg_category


@pytest.mark.parametrize("mm,expected", [
    (0.0, None), (0.4, None), (0.5, "ringan"), (19.9, "ringan"), (20.0, "sedang"),
    (49.9, "sedang"), (50.0, "lebat"), (100.0, "sangat lebat"), (150.0, "ekstrem"), (400.0, "ekstrem"),
])
def test_bmkg_category_boundaries(mm, expected):
    assert bmkg_category(mm) == expected


def test_model_a_threshold_is_bmkg_sedang_lower_bound():
    assert bmkg_category(MODEL_A_THRESHOLD_MM) == "sedang"
