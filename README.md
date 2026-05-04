# DeckSweep v1

DeckSweep is a local-first Windows cleanup app that gamifies folder sorting with flashcards:
- Right swipe / `ArrowRight` = Keep
- Left swipe / `ArrowLeft` = Queue for delete
- Folder cards can be entered as subdecks or skipped
- Final action moves queue to Windows Recycle Bin

## Tech Stack
- Python 3.13
- FastAPI + Jinja templates + plain JavaScript
- SQLite persistence (`decksweep.db`)
- `send2trash` for recycle bin operations

## Run
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn decksweep.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## API
- `POST /api/session/start`
- `GET /api/session/{id}`
- `GET /api/session/{id}/deck?deck_id=...&cursor=...`
- `POST /api/session/{id}/decision`
- `POST /api/session/{id}/enter-folder`
- `POST /api/session/{id}/skip-folder`
- `GET /api/session/{id}/preview/{item_id}`
- `GET /api/session/{id}/review`
- `POST /api/session/{id}/undo`
- `POST /api/session/{id}/apply`
- `GET /api/session/{id}/summary`

## Notes
- Safe defaults skip hidden/system files unless enabled.
- Symlinks and junction/reparse points are not traversed.
- Session state is persisted in SQLite and resumable.
