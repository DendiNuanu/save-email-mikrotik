from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import psycopg2
import os
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request as StarletteRequest
from fastapi.responses import HTMLResponse

app = FastAPI()

# ==== Session Middleware ====
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "super-secret-key"))

# ==== CORS ====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== Konfigurasi Database ====
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "sslmode": os.getenv("DB_SSLMODE", "require")
}

# ==== URL Aplikasi ====
BASE_URL = os.getenv("BASE_URL", "https://save-email-mikrotik-production.up.railway.app")

# ==== Mikrotik Hotspot ====
GATEWAY_IP = os.getenv("GATEWAY_IP", "172.19.20.1")
HOTSPOT_USER = os.getenv("HOTSPOT_USER", "user")
HOTSPOT_PASS = os.getenv("HOTSPOT_PASS", "user")
DST_URL = os.getenv("DST_URL", "https://nuanu.com/")

# ==== Google OAuth ====
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# ==== DB Init ====
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trial_emails (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            is_verified BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def startup_event():
    init_db()

# ==== Simpan Email Baru (Auto-Verified) ====
@app.post("/save_trial_email")
async def save_email(request: Request):
    data = await request.json()
    email = data.get("email")
    if not email:
        return {"status": "error", "message": "Invalid email"}

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trial_emails (email, is_verified)
        VALUES (%s, TRUE)
        ON CONFLICT (email) DO UPDATE SET is_verified = TRUE
    """, (email,))
    conn.commit()
    cur.close()
    conn.close()

    return {"status": "exists", "message": "Auto-verified"}

# ==== Cek Email (Always Verified if Saved) ====
@app.post("/check_email")
async def check_email(request: Request):
    data = await request.json()
    email = data.get("email")
    if not email:
        return {"status": "error", "message": "Invalid email"}

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_verified FROM trial_emails WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row and row[0]:
        return {"status": "exists"}
    else:
        return {"status": "not_verified"}

# ==== Google Login ====
@app.get("/auth/google/login")
async def login_google(request: StarletteRequest):
    redirect_uri = f"{BASE_URL.rstrip('/')}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth_google_callback(request: StarletteRequest):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        return JSONResponse({"status": "error", "message": "Google login failed"})

    email = user_info["email"]

    # Save or update in DB as verified
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trial_emails (email, is_verified)
        VALUES (%s, TRUE)
        ON CONFLICT (email) DO UPDATE SET is_verified = TRUE
    """, (email,))
    conn.commit()
    cur.close()
    conn.close()

    login_url = (
        f"http://{GATEWAY_IP}/login?"
        f"username={HOTSPOT_USER}&password={HOTSPOT_PASS}&dst={DST_URL}"
    )
    return RedirectResponse(url=login_url)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT email, created_at FROM trial_emails ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Build simple HTML
    html = """
    <html>
      <head>
        <title>Email Dashboard</title>
        <style>
          body { font-family: Arial, sans-serif; background: #f9f9f9; padding: 20px; }
          h1 { text-align: center; }
          table { width: 100%; border-collapse: collapse; margin-top: 20px; background: white; }
          th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
          th { background: #667eea; color: white; }
          tr:nth-child(even) { background: #f2f2f2; }
        </style>
      </head>
      <body>
        <h1>📊 Collected Emails</h1>
        <table>
          <tr><th>Email</th><th>Created At</th></tr>
    """
    for email, created_at in rows:
    date_only = created_at.date()  # just get the date part
    html += f"<tr><td>{email}</td><td>{date_only}</td></tr>"


    html += """
        </table>
      </body>
    </html>
    """
    return HTMLResponse(content=html)

