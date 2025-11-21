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
    return conn # connection object to run queries

def create_app():
    app = Flask(__name__)

    # Check if service is running and database is reachable - return JSON message 
    @app.route("/health", methods=["GET"])
    def health():
        try:
            conn = get_db_connection()
            conn.close()
            return jsonify({"service": "users", "db": "connected", "status": "ok"}), 200
        except Exception as e:
            return jsonify({"service": "users", "db_error": str(e)}), 500

    # Users roles endpoint - posting the users role to the roles table in database
    @app.route("/roles/init", methods= ["POST"])
    def init_roles():
        roles = [
            ("admin", "System administrator"),
            ("user", "Regular user"),
            ("facility_manager", "Manages rooms and equipment lists, reads bookings"),
            ("moderator", "Moderates reviews only"),
            ("auditor", "Read-only access to data and logs"),
            ("service_account", "Non-human account for inter-service calls"),
        ]
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            for privilege, description in roles:
                cur.execute(
                    # Ignore if the roles already exist to avoid crashing 
                    """
                    INSERT OR IGNORE INTO roles (privilege, description)
                    VALUES (?, ?) 
                    """, 
                    (privilege, description)
                )
            conn.commit() # saves the changes to db
        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()
        return jsonify({"message": "Roles initialized (or already existed)."}), 201 # created 
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5001, debug=True)

