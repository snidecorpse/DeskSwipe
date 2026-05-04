from __future__ import annotations

import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from decksweep.db import init_db, read_conn
from decksweep.models import (
    ApplyResult,
    DecisionRequest,
    DeckResponse,
    EnterFolderRequest,
    PreviewResponse,
    ReviewResponse,
    SessionResponse,
    SkipFolderRequest,
    StartSessionRequest,
    SummaryResponse,
    UndoRequest,
)
from decksweep.services.icons import icon_bytes_for_item
from decksweep.services.preview import classify_preview, folder_preview_children, read_text_snippet
from decksweep.services.scanner import build_deck_id, build_root_deck_id, start_scan_thread
from decksweep.services.sessions import (
    apply_delete_queue,
    create_session,
    get_deck_page,
    get_file_web_data,
    get_item_for_session,
    get_latest_session,
    get_review_data,
    get_session_payload,
    get_session_root,
    get_summary,
    mark_folder_skipped,
    record_decision,
    undo_decision,
)

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="DeckSweep", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/system/select-folder")
def select_folder() -> dict:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:
        raise HTTPException(status_code=500, detail="Folder picker unavailable.") from error

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="Choose Folder Root",
            mustexist=True,
            initialdir=str(Path.home()),
        )
        root.destroy()
    except Exception as error:
        raise HTTPException(status_code=500, detail="Could not open folder picker.") from error

    return {"path": selected or None}


@app.get("/api/session/latest", response_model=SessionResponse)
def latest_session() -> SessionResponse:
    session = get_latest_session()
    if not session:
        raise HTTPException(status_code=404, detail="No resumable session found.")
    return SessionResponse(**session)


@app.post("/api/session/start", response_model=SessionResponse)
def start_session(payload: StartSessionRequest) -> SessionResponse:
    try:
        session_id, _ = create_session(
            root_path=payload.root_path,
            include_hidden=payload.include_hidden,
            order_mode=payload.order_mode,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    start_scan_thread(session_id)
    session = get_session_payload(session_id)
    if not session:
        raise HTTPException(status_code=500, detail="Failed to create session.")
    return SessionResponse(**session)


@app.get("/api/session/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    session = get_session_payload(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SessionResponse(**session)


@app.get("/api/session/{session_id}/file-web")
def file_web(
    session_id: str,
    limit: int = Query(default=72, ge=10, le=150),
) -> dict:
    try:
        return get_file_web_data(session_id=session_id, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/session/{session_id}/deck", response_model=DeckResponse)
def deck_page(
    session_id: str,
    deck_id: str | None = Query(default=None),
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=100),
    sort: str | None = Query(default=None),
    unresolved_only: bool = Query(default=True),
) -> DeckResponse:
    resolved_deck_id = deck_id or build_root_deck_id(session_id)
    try:
        data = get_deck_page(
            session_id=session_id,
            deck_id=resolved_deck_id,
            cursor=cursor,
            limit=limit,
            sort_mode=sort or "random",
            unresolved_only=unresolved_only,
        )
        return DeckResponse(**data)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/session/{session_id}/decision")
def decide(session_id: str, payload: DecisionRequest) -> dict:
    try:
        result = record_decision(
            session_id=session_id,
            item_id=payload.item_id,
            action=payload.action,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return result


@app.post("/api/session/{session_id}/enter-folder")
def enter_folder(session_id: str, payload: EnterFolderRequest) -> dict:
    item_row = get_item_for_session(session_id, payload.item_id)
    if not item_row:
        raise HTTPException(status_code=404, detail="Folder not found.")
    if str(item_row["kind"]) != "folder":
        raise HTTPException(status_code=400, detail="Only folder cards can be entered.")

    return {
        "session_id": session_id,
        "item_id": payload.item_id,
        "deck_id": build_deck_id(payload.item_id),
        "name": str(item_row["name"]),
    }


@app.post("/api/session/{session_id}/skip-folder")
def skip_folder(session_id: str, payload: SkipFolderRequest) -> dict:
    try:
        mark_folder_skipped(session_id=session_id, item_id=payload.item_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"session_id": session_id, "item_id": payload.item_id, "status": "skipped"}


@app.get("/api/session/{session_id}/preview/{item_id}", response_model=PreviewResponse)
def preview_item(session_id: str, item_id: str) -> PreviewResponse:
    item_row = get_item_for_session(session_id, item_id)
    if not item_row:
        raise HTTPException(status_code=404, detail="Item not found.")

    path_value = str(item_row["path"])
    kind = str(item_row["kind"])
    size_bytes = int(item_row["size_bytes"])
    mime = item_row["mime"]
    preview_type = classify_preview(path_value, kind, size_bytes, mime)

    content_url = None
    text_snippet = None
    folder_children: list[str] = []
    metadata_only_reason = None

    if preview_type in {"image", "video", "audio", "pdf"}:
        content_url = f"/api/session/{session_id}/preview-content/{item_id}"
    elif preview_type == "text":
        text_snippet = read_text_snippet(path_value)
        if not text_snippet:
            preview_type = "metadata"
            metadata_only_reason = "Unable to read text preview."
    elif preview_type == "folder":
        folder_children = folder_preview_children(path_value)
    else:
        metadata_only_reason = "Preview unavailable for this file type or size."

    return PreviewResponse(
        item_id=item_id,
        path=path_value,
        kind=kind,
        preview_type=preview_type,
        mime=mime,
        size_bytes=size_bytes,
        content_url=content_url,
        text_snippet=text_snippet,
        folder_children=folder_children,
        metadata_only_reason=metadata_only_reason,
    )


@app.get("/api/session/{session_id}/preview-content/{item_id}")
def preview_content(session_id: str, item_id: str) -> FileResponse:
    item_row = get_item_for_session(session_id, item_id)
    if not item_row:
        raise HTTPException(status_code=404, detail="Item not found.")
    if str(item_row["kind"]) != "file":
        raise HTTPException(status_code=400, detail="Only files can be streamed.")

    root_path = get_session_root(session_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Session not found.")

    target_path = Path(str(item_row["path"])).resolve()
    root_resolved = Path(root_path).resolve()
    try:
        target_path.relative_to(root_resolved)
    except ValueError as error:
        raise HTTPException(status_code=403, detail="File outside allowed root.") from error

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File no longer exists.")

    media_type = item_row["mime"] or "application/octet-stream"
    return FileResponse(path=str(target_path), media_type=media_type)


@app.get("/api/session/{session_id}/icon/{item_id}")
def item_icon(session_id: str, item_id: str) -> Response:
    item_row = get_item_for_session(session_id, item_id)
    if not item_row:
        raise HTTPException(status_code=404, detail="Item not found.")
    payload, media_type = icon_bytes_for_item(
        path=str(item_row["path"]),
        name=str(item_row["name"]),
        kind=str(item_row["kind"]),
        mime=item_row["mime"],
    )
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/api/session/{session_id}/open/{item_id}")
def open_in_system(session_id: str, item_id: str) -> dict:
    item_row = get_item_for_session(session_id, item_id)
    if not item_row:
        raise HTTPException(status_code=404, detail="Item not found.")
    target_path = Path(str(item_row["path"]))
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Path no longer exists.")
    try:
        if target_path.is_file():
            subprocess.Popen(["explorer", "/select,", str(target_path)])
        else:
            subprocess.Popen(["explorer", str(target_path)])
    except OSError as error:
        raise HTTPException(status_code=500, detail="Could not open File Explorer.") from error
    return {"status": "opened", "path": str(target_path)}


@app.get("/api/session/{session_id}/review", response_model=ReviewResponse)
def review(session_id: str) -> ReviewResponse:
    data = get_review_data(session_id)
    return ReviewResponse(**data)


@app.post("/api/session/{session_id}/undo")
def undo(session_id: str, payload: UndoRequest) -> dict:
    undo_decision(session_id, payload.item_id)
    return {"session_id": session_id, "item_id": payload.item_id, "status": "undone"}


@app.post("/api/session/{session_id}/apply", response_model=ApplyResult)
def apply(session_id: str) -> ApplyResult:
    try:
        data = apply_delete_queue(session_id)
        return ApplyResult(**data)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/session/{session_id}/summary", response_model=SummaryResponse)
def summary(session_id: str) -> SummaryResponse:
    try:
        data = get_summary(session_id)
        return SummaryResponse(**data)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/health")
def health() -> dict:
    with read_conn() as connection:
        session_count = connection.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()
    return {"status": "ok", "sessions": int(session_count["c"])}
