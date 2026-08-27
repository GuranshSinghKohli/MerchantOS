from merchantos_agents.selection import select_agents


def test_inventory_question_avoids_unused_agents() -> None:
    assert select_agents("Which SKUs are at stockout risk?") == ("inventory",)


def test_revenue_decline_adds_inventory() -> None:
    assert select_agents("Why is my revenue down?") == ("analytics", "inventory")


def test_customer_behavior_adds_analytics() -> None:
    assert select_agents("How is customer behavior changing?") == ("analytics", "customer")


def test_broad_health_selects_all_allowlisted() -> None:
    assert select_agents("What should I pay attention to this week?") == (
        "analytics",
        "inventory",
        "customer",
    )


def test_unknown_and_unregistered_names_are_ignored() -> None:
    assert select_agents("units remaining", ("strategy", "action_planner", "evil")) == (
        "inventory",
    )


def test_suggested_names_intersect_allowlist_only() -> None:
    assert select_agents("hello", ("customer", "strategy")) == ("customer",)


def test_empty_question_defaults_to_analytics_and_caps_at_three() -> None:
    selected = select_agents("", ("analytics", "inventory", "customer", "analytics"))
    assert selected == ("analytics", "inventory", "customer")
    assert len(selected) <= 3


def test_product_attention_uses_analytics_and_inventory() -> None:
    assert select_agents("Which products need attention?") == ("analytics", "inventory")
