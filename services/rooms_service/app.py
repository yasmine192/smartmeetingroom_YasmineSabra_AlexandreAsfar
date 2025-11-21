from flask import Flask, jsonify
import sqlite3
import os

# Connecting to the database
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "project.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # To access columns by name
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def create_app():
    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"service": "rooms", "status": "ok"}), 200

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5002, debug=True)
