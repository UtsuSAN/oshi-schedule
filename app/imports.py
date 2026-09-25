from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.collectors import CollectedPost, ManualCollector
from app.db import get_session
from app.models import Event, ImportCandidate
from app.services.admin import ArtistService, InputError
from app.services.candidates import CandidateService, ReviewConflict, parse_import
from app.services.events import as_japan_datetime
from app.services.imports import ImportService, ImportStatus

router = APIRouter(prefix="/admin", tags=["candidates"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


def _render(request: Request, name: str, context: dict, status: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name=name, context=context, status_code=status)


async def _values(request: Request) -> dict[str, str]:
    form = await request.form()
    return {key: str(value) for key, value in form.items()}


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return as_japan_datetime(value).strftime("%Y-%m-%dT%H:%M")
    if isinstance(value, time):
        return value.isoformat(timespec="minutes")
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


EDIT_FIELDS = (
    "raw_text", "source_url", "source_account", "published_at", "artist_id",
    "candidate_title", "candidate_date", "candidate_open_at", "candidate_start_at",
    "candidate_end_at", "candidate_venue", "candidate_venue_address",
    "candidate_ticket_url", "candidate_official_url", "candidate_appearance_start",
    "candidate_appearance_end", "candidate_benefit_start", "candidate_benefit_end",
    "candidate_stage_name",
)


def _import_form(request: Request, session: Session, values: dict[str, str] | None = None,
                 errors: dict[str, str] | None = None) -> HTMLResponse:
    return _render(request, "admin/import.html", {
        "form": values or {}, "errors": errors or {}, "artists": ArtistService(session).list(),
        "active_admin": "candidates",
    }, 422 if errors else 200)


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request, session: Session = Depends(get_session)):
    return _import_form(request, session)


@router.post("/import", response_class=HTMLResponse)
async def import_post(request: Request, session: Session = Depends(get_session)):
    values = await _values(request)
    try:
        parsed = parse_import(values)
        post = ManualCollector(CollectedPost(
            text=parsed.raw_text, source_url=parsed.source_url,
            source_account=parsed.source_account,
            published_at=parsed.published_at.replace(tzinfo=timezone.utc) if parsed.published_at else None,
            artist_id=parsed.artist_id,
        )).collect()[0]
        result = ImportService(session).import_post(post)
    except InputError as exc:
        return _import_form(request, session, values, exc.errors)
    except ValueError as exc:
        return _import_form(request, session, values, {"raw_text": str(exc)})
    if result.status is ImportStatus.SKIPPED:
        return RedirectResponse(f"/admin/candidates/{result.existing_candidate_id}?saved=skipped", status_code=303)
    candidate = result.candidate
    return RedirectResponse(f"/admin/candidates/{candidate.id}?saved=created", status_code=303)


@router.get("/candidates", response_class=HTMLResponse)
def candidates_page(request: Request, status: str = "pending", session: Session = Depends(get_session)):
    if status not in ("pending", "approved", "rejected"):
        status = "pending"
    artists = {artist.id: artist for artist in ArtistService(session).list()}
    return _render(request, "admin/candidates.html", {
        "candidates": CandidateService(session).list(status), "status": status,
        "artists_by_id": artists, "active_admin": "candidates", "as_japan_datetime": as_japan_datetime,
    })


def _candidate_or_404(session: Session, candidate_id: int) -> ImportCandidate:
    candidate = CandidateService(session).get(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="候補が見つかりません")
    return candidate


def _detail(request: Request, session: Session, candidate: ImportCandidate,
            values: dict[str, str] | None = None, errors: dict[str, str] | None = None,
            saved: str = "") -> HTMLResponse:
    form = values if values is not None else {key: _display(getattr(candidate, key)) for key in EDIT_FIELDS}
    duplicate = session.get(Event, candidate.duplicate_event_id) if candidate.duplicate_event_id else None
    created_event = session.get(Event, candidate.created_event_id) if candidate.created_event_id else None
    message = {"created": "候補を作成しました", "skipped": "この投稿は取り込み済みです",
               "updated": "候補を保存しました",
               "approved": "イベントを登録しました", "rejected": "候補を却下しました"}.get(saved)
    return _render(request, "admin/candidate_detail.html", {
        "candidate": candidate, "form": form, "errors": errors or {},
        "artists": ArtistService(session).list(), "duplicate": duplicate,
        "created_event": created_event, "message": message,
        "active_admin": "candidates", "as_japan_datetime": as_japan_datetime,
    }, 422 if errors else 200)


@router.get("/candidates/{candidate_id}", response_class=HTMLResponse)
def candidate_detail(candidate_id: int, request: Request, saved: str = "",
                     session: Session = Depends(get_session)):
    return _detail(request, session, _candidate_or_404(session, candidate_id), saved=saved)


@router.post("/candidates/{candidate_id}/edit", response_class=HTMLResponse)
async def candidate_edit(candidate_id: int, request: Request, session: Session = Depends(get_session)):
    candidate = _candidate_or_404(session, candidate_id)
    values = await _values(request)
    try:
        CandidateService(session).edit(candidate, values)
    except InputError as exc:
        return _detail(request, session, candidate, values, exc.errors)
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(f"/admin/candidates/{candidate_id}?saved=updated", status_code=303)


@router.post("/candidates/{candidate_id}/approve", response_class=HTMLResponse)
async def candidate_approve(candidate_id: int, request: Request, session: Session = Depends(get_session)):
    candidate = _candidate_or_404(session, candidate_id)
    values = await _values(request)
    try:
        CandidateService(session).approve(candidate, confirm_duplicate=values.get("confirm_duplicate") == "on")
    except InputError as exc:
        return _detail(request, session, candidate, errors=exc.errors)
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(f"/admin/candidates/{candidate_id}?saved=approved", status_code=303)


@router.post("/candidates/{candidate_id}/reject", response_class=HTMLResponse)
async def candidate_reject(candidate_id: int, request: Request, session: Session = Depends(get_session)):
    candidate = _candidate_or_404(session, candidate_id)
    values = await _values(request)
    try:
        CandidateService(session).reject(candidate, values.get("review_note"))
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(f"/admin/candidates/{candidate_id}?saved=rejected", status_code=303)
