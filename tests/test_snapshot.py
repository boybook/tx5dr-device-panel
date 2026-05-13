from pathlib import Path

from tx5dr_device_panel.render.snapshot import render_fixture_to_png


def test_snapshot_command_is_deterministic(tmp_path):
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    for fixture in fixtures.glob("*.json"):
        first = render_fixture_to_png(fixture, tmp_path / f"{fixture.stem}-first.png")
        second = render_fixture_to_png(fixture, tmp_path / f"{fixture.stem}-second.png")

        assert first.read_bytes() == second.read_bytes()
