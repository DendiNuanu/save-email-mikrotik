from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os

app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Konfigurasi database dari environment variable
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

# Buat tabel kalau belum ada
def init_db():
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

init_db()

@app.post("/save_trial_email")
async def save_email(request: Request):
    data = await request.json()
    email = data.get("email")

    if not email or "@" not in email:
        return {"status": "error", "message": "Invalid email"}

    try:
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
        return {"status": "error", "message": str(e)}
