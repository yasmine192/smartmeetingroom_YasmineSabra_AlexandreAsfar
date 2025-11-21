from flask import Flask, jsonify, request
import sqlite3
import os
from werkzeug.security import generate_password_hash


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
        
    """API to post user roles to the roles table in database"""

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
            for role, description in roles:
                cur.execute(
                    # Ignore if the roles already exist to avoid crashing 
                    """
                    INSERT OR IGNORE INTO roles (role, description)
                    VALUES (?, ?) 
                    """, 
                    (role, description),
                )
            conn.commit() # saves the changes to db
        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()
        return jsonify({"message": "Roles initialized (or already existed)."}), 201 # created 
    
    """API to post a new user to the users table in database"""

    @app.route("/users/register", methods= ["POST"])
    def register_user():

        # Extract the user info from the JSON object sent by postman/frontend 
        data = request.get_json() or {} # if nothing sent

        # Validate required fields
        required_fields = ["username", "email", "password", "name", "role"]
        missing_fields = []
        for field in required_fields:
            if field not in data or not data[field]:
                missing_fields.append(field)
        if missing_fields:
            return jsonify ({"error": f"Missing fields: {','.join(missing_fields)}"}), 400 # bad request

        # Extract the input 
        username = data["username"].strip()
        email = data["email"].strip()
        password = data["password"]
        name = data["name"].strip()
        role = data["role"].strip()

        # Establish database connection
        conn = get_db_connection()
        try: 
            cur = conn.cursor()

            # Find the role ID of the role in roles table
            cur.execute(
                "SELECT role_id FROM roles WHERE role = ?", (role,))
            role_row = cur.fetchone() # return a row object of role_id
            if role_row is None:
                return jsonify({"error": "Invalid role"}), 400
            
            role_id = role_row["role_id"] # extract the role_id

            # Verify uniqueness of username and email
            cur.execute(
                """
                SELECT 1 FROM users WHERE username =? or email = ?""", 
                (username, email),
            )
            if cur.fetchone():
                return jsonify({"error": "Username or email already exists"}), 409 # conflict
            
            # Hash the password 
            password_hash = generate_password_hash(password)

            # Insert the user to users table in the database
            cur.execute(
                """
                INSERT INTO users (username, email, password_hash, name, role_id)
                VALUES (?, ?, ?, ?, ?)""",
                (username, email, password_hash, name, role_id),
                )
            conn.commit()

            user_id = cur.lastrowid # user_id is the primary key

        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        
        finally:
            conn.close()
        
        # Return JSON object of user added

        return jsonify ({
            "message": "User registered successfully",
            "user": {
                "user_id": user_id,
                "username": username,
                "email": email,
                "name": name,
                "role": role

            }
        }), 201 # created





    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5001, debug=True)

