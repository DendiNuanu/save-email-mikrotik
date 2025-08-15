from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ambil konfigurasi dari environment
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "sslmode": os.getenv("DB_SSLMODE", "require")
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


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
    except Exception as e:
        print("Database initialization failed:", e)


@app.on_event("startup")
def on_startup():
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

@app.post("/check_email")
async def check_email(request: Request):
    data = await request.json()
    email = data.get("email")

    if not email or "@" not in email:
        return {"status": "error", "message": "Invalid email"}

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM trial_emails WHERE email = %s", (email,))
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return {"status": "exists" if exists else "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
