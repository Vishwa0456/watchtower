from watchtower.checks import CheckResult
from watchtower.metrics import MetricsRegistry


def test_update_sets_gauges_correctly():
    registry = MetricsRegistry()
    results = [
        CheckResult.make("cpu", 42.0, 90.0),
        CheckResult.make("memory", 95.0, 90.0),  # breached
    ]
    registry.update(results)

    output = registry.render().decode()
    assert "watchtower_cpu_percent 42.0" in output
    assert "watchtower_memory_percent 95.0" in output
    assert 'watchtower_check_breached{check_name="memory"} 1.0' in output
    assert 'watchtower_check_breached{check_name="cpu"} 0.0' in output


def test_render_includes_timestamp_metric():
    registry = MetricsRegistry()
    registry.update([CheckResult.make("cpu", 10.0, 90.0)])
    output = registry.render().decode()
    assert "watchtower_last_check_timestamp_seconds" in output


def test_two_registries_are_independent():
    """Regression check: each MetricsRegistry must use its own
    CollectorRegistry, not the global default, or two agents in the same
    process would collide on metric names.
    """
    r1 = MetricsRegistry()
    r2 = MetricsRegistry()
    r1.update([CheckResult.make("cpu", 11.0, 90.0)])
    r2.update([CheckResult.make("cpu", 99.0, 90.0)])

    assert "watchtower_cpu_percent 11.0" in r1.render().decode()
    assert "watchtower_cpu_percent 99.0" in r2.render().decode()
