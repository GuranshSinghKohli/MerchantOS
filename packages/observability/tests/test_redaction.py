from io import StringIO

from merchantos_observability import REDACTED, configure_logging, get_logger, redact_mapping


def test_redacts_tokens_and_secrets() -> None:
    result = redact_mapping(
        {
            "event": "ok",
            "authorization": "Bearer secret",
            "nested": {"access_token": "shopify-token", "shop": "acme.myshopify.com"},
        }
    )
    assert result["event"] == "ok"
    assert result["authorization"] == REDACTED
    assert result["nested"]["access_token"] == REDACTED
    assert result["nested"]["shop"] == "acme.myshopify.com"


def test_logger_redacts_token_fields() -> None:
    stream = StringIO()
    configure_logging(level="INFO", stream=stream)
    get_logger("test").info("shopify_connected", token="should-not-appear")
    output = stream.getvalue()
    assert "should-not-appear" not in output
    assert REDACTED in output
