from __future__ import annotations

import inspect
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi.routing import APIRoute

from backend.app.api.routes import demo as demo_routes
from backend.app.api.routes import signals as signals_routes
from backend.app.main import app
from backend.app.services import monitoring_service, signals_service


def _post_paths() -> list[str]:
    return sorted(
        {
            route.path
            for route in app.routes
            if isinstance(route, APIRoute) and route.methods and "POST" in route.methods
        }
    )


def test_signal_status_update_routes_unique() -> None:
    post_paths = _post_paths()
    canonical_paths = {
        "/api/signals/{business_id}/{signal_id}/status",
        "/demo/health/{business_id}/signals/{signal_id}/status",
    }

    assert post_paths.count("/api/signals/{business_id}/{signal_id}/status") == 1
    assert post_paths.count("/demo/health/{business_id}/signals/{signal_id}/status") == 1

    extra = [
        path
        for path in post_paths
        if "signals" in path and path.endswith("/status") and path not in canonical_paths
    ]
    assert not extra, f"Unexpected signal status update routes: {extra}"


def test_demo_and_real_signal_status_delegate_to_canonical_service() -> None:
    demo_source = inspect.getsource(demo_routes.update_health_signal_status)
    signals_route_source = inspect.getsource(signals_routes.update_signal_status)
    service_source = inspect.getsource(signals_service.update_signal_status)

    assert "signals_service.update_signal_status" in signals_route_source
    assert "health_signal_service.update_signal_status" in demo_source
    assert "health_signal_service.update_signal_status" in service_source


def test_monitoring_service_uses_v2_detectors_only() -> None:
    source = inspect.getsource(monitoring_service)
    assert "run_v2_detectors" in source
    assert "signals.core" not in source
    assert "generate_core_signals" not in source
