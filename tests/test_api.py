from __future__ import annotations

from fastapi.testclient import TestClient

from decksweep.main import app
from decksweep.services.scanner import scan_session
from tests.utils import workspace_temp_dir


def test_session_lifecycle_endpoints(monkeypatch) -> None:
    with workspace_temp_dir("api") as temp_root:
        (temp_root / "demo.txt").write_text("preview me", encoding="utf-8")
        nested = temp_root / "docs"
        nested.mkdir()
        (nested / "inside.txt").write_text("inside", encoding="utf-8")

        monkeypatch.setattr("decksweep.main.start_scan_thread", scan_session)
        client = TestClient(app)

        start_response = client.post(
            "/api/session/start",
            json={"root_path": str(temp_root), "include_hidden": False, "order_mode": "random"},
        )
        assert start_response.status_code == 200
        session = start_response.json()
        session_id = session["session_id"]
        assert session["status"] == "ready"

        deck_response = client.get(f"/api/session/{session_id}/deck")
        assert deck_response.status_code == 200
        deck_payload = deck_response.json()
        assert "items" in deck_payload
        assert len(deck_payload["items"]) >= 1
        item = deck_payload["items"][0]

        decide_response = client.post(
            f"/api/session/{session_id}/decision",
            json={"item_id": item["id"], "action": "delete"},
        )
        assert decide_response.status_code == 200

        review_response = client.get(f"/api/session/{session_id}/review")
        assert review_response.status_code == 200
        review_payload = review_response.json()
        assert review_payload["delete_count"] >= 1

        preview_response = client.get(f"/api/session/{session_id}/preview/{item['id']}")
        assert preview_response.status_code == 200

        web_response = client.get(f"/api/session/{session_id}/file-web?limit=20")
        assert web_response.status_code == 200
        web_payload = web_response.json()
        assert "nodes" in web_payload
        assert web_payload["indexed_count"] >= 2

        undo_response = client.post(
            f"/api/session/{session_id}/undo",
            json={"item_id": item["id"]},
        )
        assert undo_response.status_code == 200

        review_after_undo = client.get(f"/api/session/{session_id}/review").json()
        assert review_after_undo["delete_count"] == 0
