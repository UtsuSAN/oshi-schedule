from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Appearance, Artist, Event, Source
from app.services.admin import (AdminEventService, ArtistService, InputError, event_is_past,
                                parse_appearance, parse_artist, parse_event, parse_source,
                                source_has_content)
from app.services.events import as_japan_datetime
from app.services.candidates import CandidateService

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

MESSAGES = {
    "artist_created": "アーティストを登録しました",
    "artist_updated": "アーティストを更新しました",
    "event_created": "イベントを登録しました",
    "event_updated": "イベントを更新しました",
    "appearance_created": "出演情報を追加しました",
    "appearance_updated": "出演情報を更新しました",
    "source_created": "出典を追加しました",
    "source_updated": "出典を更新しました",
}


def _render(request: Request, name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)


async def _values(request: Request) -> dict[str, str]:
    form = await request.form()
    return {key: str(value) for key, value in form.items()}


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        local = as_japan_datetime(value)
        return local.strftime("%Y-%m-%dT%H:%M") if local else ""
    if isinstance(value, (date, time)):
        return value.isoformat(timespec="minutes") if isinstance(value, time) else value.isoformat()
    return str(value)


def _model_values(obj: object | None, fields: tuple[str, ...]) -> dict[str, str]:
    return {field: _display(getattr(obj, field, None)) for field in fields}


ARTIST_FIELDS = ("name", "display_name", "x_username", "official_url")
EVENT_FIELDS = ("title", "event_date", "open_at", "start_at", "end_at", "venue_name",
                "venue_address", "ticket_url", "ticket_release_date", "ticket_release_time", "official_url", "status")
APPEARANCE_FIELDS = ("artist_id", "appearance_start_at", "appearance_end_at",
                     "benefit_start_at", "benefit_end_at", "stage_name", "notes")
SOURCE_FIELDS = ("source_type", "source_url", "source_account", "source_text", "published_at")


def _artist_or_404(session: Session, artist_id: int) -> Artist:
    artist = ArtistService(session).get(artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="アーティストが見つかりません")
    return artist


def _event_or_404(session: Session, event_id: int) -> Event:
    event = AdminEventService(session).get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="イベントが見つかりません")
    return event


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    return _render(request, "admin/index.html", {
        "artist_count": ArtistService(session).count(),
        "event_count": AdminEventService(session).count(),
        "pending_count": CandidateService(session).count_pending(),
        "active_admin": "home",
    })


@router.get("/artists", response_class=HTMLResponse)
def artists_page(request: Request, saved: str = "", session: Session = Depends(get_session)):
    return _render(request, "admin/artists.html", {
        "artists": ArtistService(session).list(), "active_admin": "artists",
        "message": MESSAGES.get(saved),
    })


def _artist_form(request: Request, artist: Artist | None, values: dict[str, str] | None = None,
                 errors: dict[str, str] | None = None) -> HTMLResponse:
    form = values if values is not None else _model_values(artist, ARTIST_FIELDS)
    enabled = (values.get("enabled") == "on") if values is not None else (artist.enabled if artist else True)
    return _render(request, "admin/artist_form.html", {
        "artist": artist, "form": form, "enabled": enabled, "errors": errors or {},
        "active_admin": "artists",
    }, 422 if errors else 200)


@router.get("/artists/new", response_class=HTMLResponse)
def new_artist_page(request: Request):
    return _artist_form(request, None)


@router.post("/artists/new", response_class=HTMLResponse)
async def create_artist(request: Request, session: Session = Depends(get_session)):
    values = await _values(request)
    try:
        ArtistService(session).save(parse_artist(values))
    except InputError as exc:
        return _artist_form(request, None, values, exc.errors)
    return RedirectResponse("/admin/artists?saved=artist_created", status_code=303)


@router.get("/artists/{artist_id}/edit", response_class=HTMLResponse)
def edit_artist_page(artist_id: int, request: Request, session: Session = Depends(get_session)):
    return _artist_form(request, _artist_or_404(session, artist_id))


@router.post("/artists/{artist_id}/edit", response_class=HTMLResponse)
async def update_artist(artist_id: int, request: Request, session: Session = Depends(get_session)):
    artist = _artist_or_404(session, artist_id)
    values = await _values(request)
    try:
        ArtistService(session).save(parse_artist(values), artist)
    except InputError as exc:
        return _artist_form(request, artist, values, exc.errors)
    return RedirectResponse("/admin/artists?saved=artist_updated", status_code=303)


@router.get("/events", response_class=HTMLResponse)
def events_page(request: Request, saved: str = "", session: Session = Depends(get_session)):
    return _render(request, "admin/events.html", {
        "events": AdminEventService(session).list(), "active_admin": "events",
        "message": MESSAGES.get(saved), "event_is_past": event_is_past,
    })


def _event_form(request: Request, session: Session, event: Event | None,
                values: dict[str, str] | None = None,
                errors: dict[str, str] | None = None, saved: str = "") -> HTMLResponse:
    form = values if values is not None else _model_values(event, EVENT_FIELDS)
    form.setdefault("status", "scheduled")
    appearance_form = values if values is not None else {"artist_id": ""}
    source_form = values if values is not None else {"source_type": "manual"}
    return _render(request, "admin/event_form.html", {
        "event": event, "form": form, "appearance_form": appearance_form,
        "source_form": source_form, "errors": errors or {},
        "artists": ArtistService(session).list(), "active_admin": "events",
        "message": MESSAGES.get(saved),
    }, 422 if errors else 200)


@router.get("/events/new", response_class=HTMLResponse)
def new_event_page(request: Request, session: Session = Depends(get_session)):
    return _event_form(request, session, None)


@router.post("/events/new", response_class=HTMLResponse)
async def create_event(request: Request, session: Session = Depends(get_session)):
    values = await _values(request)
    errors: dict[str, str] = {}
    event_data = appearance_data = source_data = None
    for parser, name in ((parse_event, "event"), (parse_appearance, "appearance")):
        try:
            if name == "event":
                event_data = parser(values)
            else:
                appearance_data = parser(values)
        except InputError as exc:
            errors.update(exc.errors)
    if source_has_content(values):
        try:
            source_data = parse_source(values)
        except InputError as exc:
            errors.update(exc.errors)
    if errors:
        return _event_form(request, session, None, values, errors)
    try:
        event = AdminEventService(session).create(event_data, appearance_data, source_data)
    except InputError as exc:
        return _event_form(request, session, None, values, exc.errors)
    return RedirectResponse(f"/admin/events/{event.id}/edit?saved=event_created", status_code=303)


@router.get("/events/{event_id}/edit", response_class=HTMLResponse)
def edit_event_page(event_id: int, request: Request, saved: str = "",
                    session: Session = Depends(get_session)):
    return _event_form(request, session, _event_or_404(session, event_id), saved=saved)


@router.post("/events/{event_id}/edit", response_class=HTMLResponse)
async def update_event(event_id: int, request: Request, session: Session = Depends(get_session)):
    event = _event_or_404(session, event_id)
    values = await _values(request)
    try:
        AdminEventService(session).update(event, parse_event(values))
    except InputError as exc:
        return _event_form(request, session, event, values, exc.errors)
    return RedirectResponse(f"/admin/events/{event_id}/edit?saved=event_updated", status_code=303)


def _appearance_or_404(event: Event, appearance_id: int) -> Appearance:
    appearance = next((item for item in event.appearances if item.id == appearance_id), None)
    if appearance is None:
        raise HTTPException(status_code=404, detail="出演情報が見つかりません")
    return appearance


def _appearance_form(request: Request, session: Session, event: Event,
                     appearance: Appearance | None, values: dict[str, str] | None = None,
                     errors: dict[str, str] | None = None) -> HTMLResponse:
    return _render(request, "admin/appearance_form.html", {
        "event": event, "appearance": appearance,
        "form": values if values is not None else _model_values(appearance, APPEARANCE_FIELDS),
        "artists": ArtistService(session).list(), "errors": errors or {},
        "active_admin": "events",
    }, 422 if errors else 200)


@router.get("/events/{event_id}/appearances/new", response_class=HTMLResponse)
def new_appearance_page(event_id: int, request: Request, session: Session = Depends(get_session)):
    return _appearance_form(request, session, _event_or_404(session, event_id), None)


@router.post("/events/{event_id}/appearances/new", response_class=HTMLResponse)
async def create_appearance(event_id: int, request: Request, session: Session = Depends(get_session)):
    event = _event_or_404(session, event_id)
    values = await _values(request)
    try:
        AdminEventService(session).save_appearance(event, parse_appearance(values))
    except InputError as exc:
        return _appearance_form(request, session, event, None, values, exc.errors)
    return RedirectResponse(f"/admin/events/{event_id}/edit?saved=appearance_created", status_code=303)


@router.get("/events/{event_id}/appearances/{appearance_id}/edit", response_class=HTMLResponse)
def edit_appearance_page(event_id: int, appearance_id: int, request: Request,
                         session: Session = Depends(get_session)):
    event = _event_or_404(session, event_id)
    return _appearance_form(request, session, event, _appearance_or_404(event, appearance_id))


@router.post("/events/{event_id}/appearances/{appearance_id}/edit", response_class=HTMLResponse)
async def update_appearance(event_id: int, appearance_id: int, request: Request,
                            session: Session = Depends(get_session)):
    event = _event_or_404(session, event_id)
    appearance = _appearance_or_404(event, appearance_id)
    values = await _values(request)
    try:
        AdminEventService(session).save_appearance(event, parse_appearance(values), appearance)
    except InputError as exc:
        return _appearance_form(request, session, event, appearance, values, exc.errors)
    return RedirectResponse(f"/admin/events/{event_id}/edit?saved=appearance_updated", status_code=303)


def _source_or_404(event: Event, source_id: int) -> Source:
    source = next((item for item in event.sources if item.id == source_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail="出典が見つかりません")
    return source


def _source_form(request: Request, event: Event, source: Source | None,
                 values: dict[str, str] | None = None,
                 errors: dict[str, str] | None = None) -> HTMLResponse:
    form = values if values is not None else _model_values(source, SOURCE_FIELDS)
    form.setdefault("source_type", "manual")
    return _render(request, "admin/source_form.html", {
        "event": event, "source": source, "form": form, "errors": errors or {},
        "active_admin": "events",
    }, 422 if errors else 200)


@router.get("/events/{event_id}/sources/new", response_class=HTMLResponse)
def new_source_page(event_id: int, request: Request, session: Session = Depends(get_session)):
    return _source_form(request, _event_or_404(session, event_id), None)


@router.post("/events/{event_id}/sources/new", response_class=HTMLResponse)
async def create_source(event_id: int, request: Request, session: Session = Depends(get_session)):
    event = _event_or_404(session, event_id)
    values = await _values(request)
    try:
        AdminEventService(session).save_source(event, parse_source(values))
    except InputError as exc:
        return _source_form(request, event, None, values, exc.errors)
    return RedirectResponse(f"/admin/events/{event_id}/edit?saved=source_created", status_code=303)


@router.get("/events/{event_id}/sources/{source_id}/edit", response_class=HTMLResponse)
def edit_source_page(event_id: int, source_id: int, request: Request,
                     session: Session = Depends(get_session)):
    event = _event_or_404(session, event_id)
    return _source_form(request, event, _source_or_404(event, source_id))


@router.post("/events/{event_id}/sources/{source_id}/edit", response_class=HTMLResponse)
async def update_source(event_id: int, source_id: int, request: Request,
                        session: Session = Depends(get_session)):
    event = _event_or_404(session, event_id)
    source = _source_or_404(event, source_id)
    values = await _values(request)
    try:
        AdminEventService(session).save_source(event, parse_source(values), source)
    except InputError as exc:
        return _source_form(request, event, source, values, exc.errors)
    return RedirectResponse(f"/admin/events/{event_id}/edit?saved=source_updated", status_code=303)
