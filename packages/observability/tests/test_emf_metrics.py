from merchantos_observability.metrics import emit_metric


def test_emit_metric_redacts_sensitive_dimensions(capsys, monkeypatch) -> None:
    monkeypatch.setenv("AWS_EMF_NAMESPACE", "MerchantOS/Test")
    emit_metric("requests", 1, dimensions={"path": "/health", "token": "shpua_secret"})
    out = capsys.readouterr().out
    assert "shpua_secret" not in out
    assert "MerchantOS/Test" in out
    assert "requests" in out
