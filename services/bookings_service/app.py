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
        return jsonify({"service": "bookings", "status": "ok"}), 200
    

    # GET /bookings/user/<user_id>   → returns all bookings for a user

    @app.route("/bookings/user/<int:user_id>", methods=["GET"])
    def get_bookings_by_user(user_id):
        conn = get_db_connection()
        try:
            cur = conn.cursor()

            cur.execute("""
                SELECT 
                    booking_id,
                    user_id,
                    room_id,
                    start_time,
                    end_time,
                    status,
                    created_at
                FROM bookings
                WHERE user_id = ?
                ORDER BY start_time DESC
            """, (user_id,))

            rows = cur.fetchall()

            bookings = [
                {
                    "booking_id": row["booking_id"],
                    "room_id": row["room_id"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "status": row["status"],
                    "created_at": row["created_at"]
                }
                for row in rows
            ]

        except Exception as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()

        return jsonify({"user_id": user_id, "bookings": bookings}), 200



    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5003, debug=True)
