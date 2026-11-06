
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google import genai
from google.genai import types


# ==================================================
# 1. CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SERVICE_ACCOUNT_PATH = BASE_DIR / "serviceAccountKey.json"

GEMINI_MODEL = "gemini-3.8-flash"

# Configure logging
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# ==================================================
# 2. FIREBASE INITIALIZATION
# ==================================================

if not FIREBASE_DATABASE_URL:
    raise RuntimeError(
        "FIREBASE_DATABASE_URL is missing from environment variables."
    )

# Use Render Secret File path if configured.
# Otherwise, use the local serviceAccountKey.json file.
SERVICE_ACCOUNT_PATH = Path(
    os.getenv(
        "FIREBASE_CREDENTIALS_PATH",
        str(BASE_DIR / "serviceAccountKey.json")
    )
)

if not SERVICE_ACCOUNT_PATH.is_file():
    raise RuntimeError(
        f"Firebase credentials file not found at: {SERVICE_ACCOUNT_PATH}"
    )

if not firebase_admin._apps:

    firebase_credential = credentials.Certificate(
        str(SERVICE_ACCOUNT_PATH)
    )

    firebase_admin.initialize_app(
        firebase_credential,
        {
            "databaseURL": FIREBASE_DATABASE_URL
        }
    )

print("Firebase connected successfully!")

# ==================================================
# 3. GEMINI INITIALIZATION
# ==================================================

gemini_client = None

if GEMINI_API_KEY:

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=300_000
        )
    )


# ==================================================
# 4. FASTAPI APPLICATION
# ==================================================

app = FastAPI(
    title="Smart Classroom Energy System",
    description=(
        "ESP32 sensor monitoring, Firebase storage "
        "and AI-powered energy analysis."
    ),
    version="2.0.0"
)


# ==================================================
# 5. REQUEST MODEL
# ==================================================

class Reading(BaseModel):
    timestamp: str
    motion: bool
    dark: bool
    light_on: bool


# ==================================================
# 6. HOME / HEALTH CHECK
# ==================================================

@app.get("/")
def home():

    return {
        "message": "Smart Classroom Energy System API",
        "status": "Running",
        "firebase": "Connected",
        "gemini": (
            "Configured"
            if gemini_client
            else "Missing GEMINI_API_KEY"
        ),
        "model": GEMINI_MODEL
    }

@app.get("/health")
def health():
    return {"status": "ok"}


# ==================================================
# 7. RECEIVE ESP32 SENSOR DATA
# ==================================================

@app.post("/sensor")
def receive_sensor_data(reading: Reading):

    try:

        data = reading.model_dump()

        data["received_at"] = datetime.now(
            timezone.utc
        ).timestamp()

        # Save reading in Firebase
        reading_ref = db.reference(
            "classroom_data"
        ).push(data)

        # Update latest system status
        db.reference("system_status").set({
            **data,
            "record_id": reading_ref.key
        })

        logger.info("Sensor reading saved successfully.")

        return {
            "success": True,
            "message": "Sensor data saved successfully",
            "record_id": reading_ref.key
        }

    except Exception as exc:

        logger.exception("Sensor data saving failed.")

        raise HTTPException(
            status_code=500,
            detail="Failed to save sensor data to Firebase."
        ) from exc


# ==================================================
# 8. GET SENSOR READINGS
# ==================================================

@app.get("/readings")
def get_readings():

    try:

        stored_data = db.reference(
            "classroom_data"
        ).get()

        if not stored_data:
            return {
                "readings": [],
                "count": 0
            }

        readings = []

        for record_id, record in stored_data.items():

            if isinstance(record, dict):

                readings.append({
                    **record,
                    "id": record_id
                })

        # Latest records first
        readings.sort(
            key=lambda item: item.get("received_at", 0),
            reverse=True
        )

        return {
            "readings": readings[:100],
            "count": len(readings)
        }

    except Exception as exc:

        logger.exception("Reading retrieval failed.")

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve sensor readings."
        ) from exc


# ==================================================
# 9. GENERATE AI ENERGY ANALYSIS
# ==================================================

@app.post("/analyze")
def analyze_energy():

    if gemini_client is None:

        raise HTTPException(
            status_code=503,
            detail=(
                "Gemini API is not configured. "
                "Check GEMINI_API_KEY in backend/.env."
            )
        )

    try:

        logger.info("Starting AI energy analysis.")

        # ------------------------------------------
        # Fetch Firebase readings
        # ------------------------------------------

        stored_data = db.reference(
            "classroom_data"
        ).get()

        if not stored_data:

            raise HTTPException(
                status_code=400,
                detail=(
                    "No sensor readings available. "
                    "Send readings from ESP32 first."
                )
            )

        readings = []

        for record_id, record in stored_data.items():

            if isinstance(record, dict):

                readings.append({
                    **record,
                    "id": record_id
                })

        if not readings:

            raise HTTPException(
                status_code=400,
                detail="No valid sensor records found."
            )

        readings.sort(
            key=lambda item: item.get("received_at", 0),
            reverse=True
        )

        # ------------------------------------------
        # Calculate statistics from ALL readings
        # ------------------------------------------

        total = len(readings)

        motion_count = sum(
            bool(item.get("motion", False))
            for item in readings
        )

        dark_count = sum(
            bool(item.get("dark", False))
            for item in readings
        )

        light_on_count = sum(
            bool(item.get("light_on", False))
            for item in readings
        )

        light_on_percentage = round(
            (light_on_count / total) * 100,
            1
        )

        motion_percentage = round(
            (motion_count / total) * 100,
            1
        )

        dark_percentage = round(
            (dark_count / total) * 100,
            1
        )

        # ------------------------------------------
        # Prepare a smaller Gemini input
        # ------------------------------------------

        latest_readings = readings[:25]

        # Keep only useful fields in the AI sample
        sample_data = [
            {
                "timestamp": item.get("timestamp"),
                "motion": item.get("motion"),
                "dark": item.get("dark"),
                "light_on": item.get("light_on")
            }
            for item in latest_readings
        ]

        statistics = {
            "total_readings": total,
            "motion_detected": motion_count,
            "dark_detected": dark_count,
            "light_on_count": light_on_count,
            "motion_percentage": motion_percentage,
            "dark_percentage": dark_percentage,
            "light_on_percentage": light_on_percentage
        }

        # ------------------------------------------
        # Prepare AI prompt
        # ------------------------------------------

        prompt = f"""
You are an expert school energy-efficiency analyst.

Analyse the following Smart Classroom monitoring data
collected using an ESP32, PIR motion sensor and LDR
light sensor.

OVERALL STATISTICS:
{statistics}

LATEST SENSOR READINGS (maximum 25):
{sample_data}

Prepare a professional but easy-to-understand report
for school management.

Use the following sections:

1. Overall Energy Status
Explain the general classroom lighting situation.

2. Sensor Observations
Explain the motion, darkness and light patterns.

3. Energy Wastage Possibilities
Identify possible situations where electricity
may be wasted.

4. Recommendations
Give three practical recommendations to save energy.

5. System Improvements
Suggest improvements to the smart classroom system.

6. Conclusion
Summarise how this system supports energy conservation.

IMPORTANT INSTRUCTIONS:

- Use the overall statistics for numerical observations.
- Use the latest readings only as a sample of recent activity.
- Do not claim that electricity consumption was measured.
- Do not invent electricity bills, rupee savings or carbon savings.
- Distinguish actual observations from assumptions.
- Mention that sensor readings alone cannot calculate
  actual electricity consumption.
- Keep the report concise and practical.
"""

        # ------------------------------------------
        # Generate report using Gemini Interactions API
        # ------------------------------------------

        logger.info(
            "Sending %s readings summary to Gemini.",
            len(sample_data)
        )

        interaction = gemini_client.interactions.create(
            model=GEMINI_MODEL,
            input=prompt
        )

        report_text = interaction.output_text

        if not report_text or not report_text.strip():

            raise HTTPException(
                status_code=502,
                detail="Gemini returned an empty analysis."
            )

        # ------------------------------------------
        # Save AI report in Firebase
        # ------------------------------------------

        report_data = {
            "report": report_text,
            "model": GEMINI_MODEL,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "readings_analyzed": total,
            "statistics": statistics
        }

        report_ref = db.reference(
            "ai_reports"
        ).push(report_data)

        logger.info(
            "AI report generated and saved: %s",
            report_ref.key
        )

        return {
            "success": True,
            "message": "AI report generated successfully",
            "report_id": report_ref.key,
            "report": report_text,
            "model": GEMINI_MODEL,
            "readings_analyzed": total,
            "statistics": statistics
        }

    except HTTPException:

        raise

    except Exception as exc:

        logger.exception("AI energy analysis failed.")

        raise HTTPException(
            status_code=502,
            detail=f"AI energy analysis failed: {str(exc)}"
        ) from exc


# ==================================================
# 10. GET PREVIOUS AI REPORTS
# ==================================================

@app.get("/reports")
def get_reports():

    try:

        stored_reports = db.reference(
            "ai_reports"
        ).get()

        if not stored_reports:

            return {
                "reports": [],
                "count": 0
            }

        reports = []

        for report_id, report in stored_reports.items():

            if isinstance(report, dict):

                reports.append({
                    **report,
                    "id": report_id
                })

        reports.sort(
            key=lambda item: item.get("created_at", ""),
            reverse=True
        )

        return {
            "reports": reports[:50],
            "count": len(reports)
        }

    except Exception as exc:

        logger.exception("AI report retrieval failed.")

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve AI reports."
        ) from exc
