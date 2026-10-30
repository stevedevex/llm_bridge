

from bridge_kit.cli import main


def test_a_usage_error_exits_2():
    assert main(["validate", "mapping"]) == 2
    assert main(["validate", "mapping", "missing.md", "--model", "nowhere"]) == 2
