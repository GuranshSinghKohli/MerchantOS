from merchantos_shopify.mutator import (
    AdapterShopifyMutator,
    FakeShopifyMutator,
    assert_no_generic_execute,
)


def test_mutators_have_no_generic_execute() -> None:
    fake = FakeShopifyMutator()
    assert_no_generic_execute(fake)
    assert_no_generic_execute(AdapterShopifyMutator.__dict__)
    for name in ("execute", "request", "graphql", "raw", "execute_shopify_request"):
        assert not hasattr(FakeShopifyMutator, name)
        assert name not in AdapterShopifyMutator.__dict__
