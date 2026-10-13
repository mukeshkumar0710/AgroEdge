"""
Configuration settings for the Telemetry & ML Pipeline.
"""
import os

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
CORS_ORIGINS = ["*"]

# Geospatial default bounds (centered around India / South Asia, customizable)
DEFAULT_CENTER_LAT = 20.5937
DEFAULT_CENTER_LNG = 78.9629

# Maximum allowable image payload size (15MB raw upload cap)
MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024
