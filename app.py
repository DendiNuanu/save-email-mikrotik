from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
import psycopg2
import os
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request as StarletteRequest

app = FastAPI()

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

# ==== Email SMTP (untuk verifikasi manual) ====
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ==== URL Aplikasi ====
BASE_URL = os.getenv("BASE_URL", "https://save-email-mikrotik-production.up.railway.app")

# ==== Mikrotik Hotspot ====
GATEWAY_IP = os.getenv("GATEWAY_IP", "172.19.20.1")  # IP hotspot Mikrotik
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
            is_verified BOOLEAN DEFAULT FALSE,
            verify_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def startup_event():
    init_db()

# ==== Kirim Email Verifikasi ====
def send_verification_email(email, token):
    link = f"{BASE_URL.rstrip('/')}/verify?token={token}"
    subject = "Verify your email to connect to Free WiFi"
    body = f"""
    Hello,

    Please click the link below to verify your email and connect to Free WiFi:
    {link}

    If you didn't request this, please ignore this email.

    Regards,
    Free WiFi Admin
    """
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, email, msg.as_string())

# ==== Simpan Email Baru ====
@app.post("/save_trial_email")
async def save_email(request: Request):
    data = await request.json()
    email = data.get("email")
    if not email or "@" not in email:
        return {"status": "error", "message": "Invalid email"}

    token = str(uuid.uuid4())
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trial_emails (email, verify_token)
        VALUES (%s, %s)
        ON CONFLICT (email) DO UPDATE SET verify_token = EXCLUDED.verify_token
    """, (email, token))
    conn.commit()
    cur.close()
    conn.close()

    send_verification_email(email, token)
    return {"status": "pending", "message": "Verification email sent"}

# ==== Cek Email ====
@app.post("/check_email")
async def check_email(request: Request):
    data = await request.json()
    email = data.get("email")
    if not email or "@" not in email:
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

# ==== Verifikasi Token & Auto Login ====
@app.get("/verify")
async def verify_email(token: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE trial_emails SET is_verified = TRUE
        WHERE verify_token = %s RETURNING email
    """, (token,))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if row:
        login_url = (
            f"http://{GATEWAY_IP}/login?"
            f"username={HOTSPOT_USER}&password={HOTSPOT_PASS}&dst={DST_URL}"
        )
        return RedirectResponse(url=login_url)
    else:
        return JSONResponse({"status": "error", "message": "Invalid token"})

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

    # Save or update in DB
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

    # Auto-login Mikrotik
    login_url = (
        f"http://{GATEWAY_IP}/login?"
        f"username={HOTSPOT_USER}&password={HOTSPOT_PASS}&dst={DST_URL}"
    )
    return RedirectResponse(url=login_url)
