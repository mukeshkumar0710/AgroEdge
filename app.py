"""
FastAPI Server for Edge PWA Ingestion, Async ML Pipeline, and Live Government Dashboard.
"""
import os
import json
import uuid
import datetime
import asyncio
from typing import AsyncGenerator
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS, MAX_IMAGE_SIZE_BYTES
from .models import (
    IngestionResponse,
    GeoJSONFeatureCollection,
    GeoJSONFeature,
    GeoJSONGeometry,
    IncidentProperties,
    SimulationRequest
)
from .ml_pipeline import classifier_service
from .localization import get_localized_treatment
from .geo_store import geo_store

app = FastAPI(
    title="Edge-to-Command Geospatial AI System",
    description="Asynchronous telemetry ingestion, edge PWA sync, and real-time government analytical dashboard.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def async_worker_process_payload(
    incident_id: str,
    image_bytes: bytes,
    lat: float,
    lng: float,
    lang_code: str,
    client_timestamp: str
):
    """
    Non-blocking background worker:
    1. Analyzes image through AsyncMLClassifier.
    2. Builds localized treatment instructions.
    3. Formats GeoJSON Feature according to RFC 7946.
    4. Pushes to spatial store and broadcasts to active command dashboards.
    """
    try:
        # 1. Run ML classification
        ml_prediction = await classifier_service.predict_image(image_bytes)

        # 2. Derive localized treatment
        condition = ml_prediction["condition"]
        localized_data = get_localized_treatment(condition, lang_code)

        # 3. Build RFC 7946 compliant GeoJSON Feature ([lng, lat])
        feature = GeoJSONFeature(
            id=incident_id,
            geometry=GeoJSONGeometry(
                type="Point",
                coordinates=[lng, lat]
            ),
            properties=IncidentProperties(
                incident_id=incident_id,
                condition=localized_data["title"],
                category=ml_prediction["category"],
                confidence=ml_prediction["confidence"],
                severity=ml_prediction["severity"],
                treatment_plan=localized_data["treatment_plan"],
                language=localized_data["language_applied"],
                timestamp=client_timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                reported_lat=lat,
                reported_lng=lng,
                agent_id="field-pwa-edge"
            )
        )

        # 4. Save and broadcast to dashboards
        await geo_store.add_and_broadcast(feature)

    except Exception as exc:
        print(f"[Worker Error] Processing incident {incident_id} failed: {exc}")

@app.post("/api/v1/diagnose-and-report", response_model=IngestionResponse)
async def diagnose_and_report_endpoint(
    background_tasks: BackgroundTasks,
    client_incident_id: str = Form(..., description="Unique client UUID for idempotency"),
    latitude: float = Form(..., description="WGS84 Latitude"),
    longitude: float = Form(..., description="WGS84 Longitude"),
    language_code: str = Form(default="en", description="Target language: en, hi, ta, te, es, bn"),
    captured_at: str = Form(default="", description="ISO timestamp from edge device"),
    image: UploadFile = File(...)
):
    """
    Primary ingestion endpoint for Edge PWA offline sync.
    Returns HTTP 200 within <40ms while queuing ML inference in the background.
    """
    # 1. Idempotency Check
    if geo_store.is_duplicate(client_incident_id):
        return IngestionResponse(
            client_incident_id=client_incident_id,
            status="acknowledged_duplicate",
            message="Incident has already been processed and recorded.",
            received_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )

    # 2. Payload validation
    geo_store.register_id(client_incident_id)
    image_bytes = await image.read()

    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Image size exceeds permissible limit.")

    # 3. Offload compute to background task
    background_tasks.add_task(
        async_worker_process_payload,
        incident_id=client_incident_id,
        image_bytes=image_bytes,
        lat=latitude,
        lng=longitude,
        lang_code=language_code,
        client_timestamp=captured_at
    )

    return IngestionResponse(
        client_incident_id=client_incident_id,
        status="queued",
        message="Queued for async neural classification, localization, and geospatial broadcast.",
        received_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

@app.get("/api/v1/incidents/geojson", response_model=GeoJSONFeatureCollection)
async def get_all_incidents_geojson():
    """
    Returns full GeoJSON FeatureCollection of historical and active incidents
    for initial Leaflet map layer hydration.
    """
    return geo_store.get_feature_collection()

@app.get("/api/v1/dashboard/stream")
async def sse_dashboard_stream():
    """
    Server-Sent Events endpoint streaming real-time GeoJSON features
    as field agents upload edge triage records.
    """
    subscriber_queue = geo_store.subscribe()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial keep-alive ping
            yield "event: ping\ndata: {}\n\n"
            while True:
                feature_dict = await subscriber_queue.get()
                yield f"data: {json.dumps(feature_dict)}\n\n"
        except asyncio.CancelledError:
            geo_store.unsubscribe(subscriber_queue)
        except Exception:
            geo_store.unsubscribe(subscriber_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/v1/simulate-incident")
async def simulate_incident(req: SimulationRequest):
    """
    Testing / Demo endpoint: Simulates an edge detection event
    and immediately pumps a GeoJSON feature into the live dashboard.
    """
    sim_id = f"sim-{uuid.uuid4().hex[:8]}"
    lat = req.latitude if req.latitude is not None else 21.0 + (hash(sim_id) % 800) / 100.0
    lng = req.longitude if req.longitude is not None else 75.0 + (hash(sim_id) % 900) / 100.0
    lang = req.language_code or "en"
    cond = req.condition or "PestInfestation"
    sev = req.severity or "HIGH"

    loc = get_localized_treatment(cond, lang)

    feature = GeoJSONFeature(
        id=sim_id,
        geometry=GeoJSONGeometry(
            type="Point",
            coordinates=[lng, lat]
        ),
        properties=IncidentProperties(
            incident_id=sim_id,
            condition=loc["title"],
            category="Simulation",
            confidence=0.95,
            severity=sev,  # type: ignore
            treatment_plan=loc["treatment_plan"],
            language=loc["language_applied"],
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            reported_lat=lat,
            reported_lng=lng,
            agent_id="test-simulator"
        )
    )

    await geo_store.add_and_broadcast(feature)
    return {"status": "broadcasted", "feature": feature.model_dump()}

@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Edge PWA & Geospatial Command Hub",
        "cached_incidents": len(geo_store.features),
        "active_subscribers": len(geo_store.subscribers)
    }

@app.get("/dashboard", include_in_schema=False)
async def dashboard_redirect():
    return RedirectResponse(url="/dashboard/", status_code=307)

# Mount frontend PWA and government command dashboard static directories
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
dashboard_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))

if os.path.isdir(dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

