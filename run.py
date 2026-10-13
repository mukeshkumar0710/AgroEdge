"""
Unified Runner Script for the Full-Stack Edge PWA & Geospatial Command Hub.
Executes the FastAPI server with auto-reload.
"""
import sys
import uvicorn
from backend.config import HOST, PORT

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    print("=" * 70)
    print("  * AGROEDGE TELEMETRY & COMMAND PLATFORM")
    print("=" * 70)
    print(f"  * Mobile PWA Field Client:     http://localhost:{PORT}/")
    print(f"  * Government Command Center:   http://localhost:{PORT}/dashboard")
    print(f"  * REST & SSE API Swagger Docs: http://localhost:{PORT}/docs")
    print("=" * 70)
    uvicorn.run("backend.app:app", host=HOST, port=PORT, reload=True)
