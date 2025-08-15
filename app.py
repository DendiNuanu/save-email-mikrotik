from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os

app = FastAPI()

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database config from Railway ENV
DB_CONFIG = {
    "host": os.environ.get("DB_HOST"),
    "port": os.environ.get("DB_PORT"),
    "dbname": os.environ.get("DB_NAME"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "sslmode": os.environ.get("DB_SSLMODE", "require")
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# Inisialisasi database
def init_db():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trial_emails (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database initialized successfully.")
    except Exception as e:
        print("❌ Database initialization failed:", e)

# Jalankan saat startup
init_db()

# Handle OPTIONS (CORS preflight fix)
@app.options("/save_trial_email")
async def options_handler():
    return {}

# Endpoint untuk simpan email
@app.post("/save_trial_email")
async def save_email(request: Request):
    try:
        data = await request.json()
        email = data.get("email")

        if not email or "@" not in email:
            return {"status": "error", "message": "Invalid email format"}

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trial_emails (email) VALUES (%s) ON CONFLICT (email) DO NOTHING",
            (email,)
        )
        conn.commit()
        cur.close()
        conn.close()

        return {"status": "success", "message": "Email saved"}
    except Exception as e:
        print("❌ Error saving email:", e)
        return {"status": "error", "message": str(e)}
