"""Model A tetap bisa dimuat dari salinan lokal saat server MLflow mati."""

import json

import mlflow
import mlflow.sklearn  # modul lazy: import eksplisit supaya monkeypatch mengenai objek yang sama
import pytest

from pipeline import predict


class DownClient:
    def get_model_version_by_alias(self, *_):
        raise ConnectionError("MLflow mati")


def test_uses_cached_champion_when_mlflow_down(tmp_path, monkeypatch):
    (tmp_path / "v1").mkdir()
    (tmp_path / "champion.json").write_text(json.dumps({"model": predict.MODEL_NAME, "version": "1"}))
    monkeypatch.setattr(mlflow, "MlflowClient", DownClient)
    monkeypatch.setattr("mlflow.sklearn.load_model", lambda path: f"model@{path}")
    model, version, from_cache = predict.load_champion(tmp_path)
    assert version == "1" and from_cache and model.endswith("v1")


def test_no_cache_and_mlflow_down_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(mlflow, "MlflowClient", DownClient)
    with pytest.raises(RuntimeError, match="belum ada salinan"):
        predict.load_champion(tmp_path)
