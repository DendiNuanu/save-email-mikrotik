from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request as StarletteRequest
from authlib.integrations.starlette_client import OAuth
import psycopg2
import os
import csv
from io import StringIO

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

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# ==== Dashboard Password from Environment ====
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "default-password")

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
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ==== DB Init ====
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

# ==== Dashboard Login Page ====
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_login(request: Request):
    if request.session.get("logged_in"):
        return await show_dashboard()

    html = """
    <html>
      <head>
        <title>Dashboard Login</title>
        <style>
          body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea, #764ba2);
            display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;
          }
          .login-box {
            background: white; padding: 40px; border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2); text-align: center; width: 300px;
          }
          input[type=password] { width: 100%; padding: 12px 10px; margin: 15px 0; border-radius: 6px; border: 1px solid #ccc; font-size: 16px; }
          button { background: #667eea; color: white; border: none; padding: 12px 20px; border-radius: 6px; cursor: pointer; font-size: 16px; }
          button:hover { background: #5a67d8; }
        </style>
      </head>
      <body>
        <div class="login-box">
          <h2>🔒 Dashboard Login</h2>
          <form method="post" action="/dashboard">
            <input type="password" name="password" placeholder="Enter password" required>
            <button type="submit">Login</button>
          </form>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=html)

# ==== Handle Dashboard Login ====
@app.post("/dashboard", response_class=HTMLResponse)
async def dashboard_post(request: Request, password: str = Form(...)):
    if password != DASHBOARD_PASSWORD:
        return HTMLResponse(content="<h2>❌ Invalid password</h2><a href='/dashboard'>Try again</a>", status_code=401)

    request.session["logged_in"] = True
    return await show_dashboard()

# ==== Show Dashboard ====
async def show_dashboard():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT email, created_at FROM trial_emails ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    html = """
    <html>
      <head>
        <title>Email Dashboard</title>
        <style>
          body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f3f4f6; padding: 20px; }
          h1 { text-align: center; color: #333; }
          table { width: 100%; border-collapse: collapse; margin-top: 20px; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
          th, td { padding: 12px 15px; text-align: left; }
          th { background: #667eea; color: white; }
          tr:nth-child(even) { background: #f2f2f2; }
          .logout, .download { display: inline-block; margin: 10px; text-decoration: none; font-weight: bold; padding: 10px 15px; border-radius: 6px; }
          .logout { color: #667eea; border: 1px solid #667eea; }
          .logout:hover { background: #667eea; color: white; }
          .download { background: #10b981; color: white; }
          .download:hover { background: #059669; }
          @media(max-width: 600px) { table, th, td { font-size: 14px; } }
        </style>
      </head>
      <body>
        <h1>📊 Collected Emails</h1>
        <div style="text-align:center;">
            <a href="/dashboard/logout" class="logout">Logout</a>
            <a href="/dashboard/download" class="download">Download CSV</a>
        </div>
        <table>
          <tr><th>Email</th><th>Created At</th></tr>
    """
    for email, created_at in rows:
        html += f"<tr><td>{email}</td><td>{created_at.date()}</td></tr>"

    html += "</table></body></html>"
    return HTMLResponse(content=html)

# ==== Dashboard Logout ====
@app.get("/dashboard/logout")
async def dashboard_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/dashboard")

# ==== Download CSV ====
@app.get("/dashboard/download")
async def download_csv(request: Request):
    if not request.session.get("logged_in"):
        return RedirectResponse("/dashboard")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT email, created_at FROM trial_emails ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    csv_file = StringIO()
    writer = csv.writer(csv_file)
    writer.writerow(["Email", "Created At"])
    for email, created_at in rows:
        writer.writerow([email, created_at.date()])

    csv_file.seek(0)
    return StreamingResponse(
        csv_file,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=emails.csv"}
    )
