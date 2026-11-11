import pytest

import nba_props.model as nba_model


@pytest.fixture(autouse=True)
def allow_unders(request):
    """The fake leagues are built for pipeline mechanics, and most of their edges are unders, so tests
    run with the NBA over-only rule off unless they opt in with @pytest.mark.no_unders."""
    saved = nba_model.NO_UNDERS
    nba_model.NO_UNDERS = request.node.get_closest_marker("no_unders") is not None
    yield
    nba_model.NO_UNDERS = saved


def pytest_configure(config):
    config.addinivalue_line("markers", "no_unders: run with the NBA over-only rule on")
