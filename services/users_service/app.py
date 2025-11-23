from flask import Flask, jsonify, request
import requests
import sqlite3
import os
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask_jwt_extended import JWTManager, create_access_token
from datetime import timedelta
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt


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

    app.config["JWT_SECRET_KEY"] = "secret_key"   
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1) # The token expires in one hour
    jwt = JWTManager(app)

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
    
    """API to initialize the admim's profile to the database"""

    @app.route("/admin/init", methods=["POST"])
    def init_admin():
        data = request.get_json() or {}
        required = ["username", "email", "password", "name"]

        for field in required:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing field: {field}"}), 400

        username = data["username"].strip()
        email = data["email"].strip()
        password = data["password"]
        name = data["name"].strip()
        role = "admin"

        conn = get_db_connection()
        try:
            cur = conn.cursor()

            # Check if any admin already exists
            cur.execute("""
                SELECT 1 FROM users u
                JOIN roles r ON u.role_id = r.role_id
                WHERE r.role = 'admin'
            """)
            if cur.fetchone():
                return jsonify({"error": "Admin already initialized"}), 403

            # Get the admin role ID
            cur.execute("SELECT role_id FROM roles WHERE role = 'admin'")
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Admin role missing from database"}), 500

            role_id = row["role_id"]

            # Check if username/email is already taken
            cur.execute("""
                SELECT 1 FROM users WHERE username=? OR email=?
            """, (username, email))
            if cur.fetchone():
                return jsonify({"error": "Username or email already exists"}), 409

            # Hash password
            password_hash = generate_password_hash(password)

            # Insert admin
            cur.execute("""
                INSERT INTO users (username, email, password_hash, name, role_id)
                VALUES (?, ?, ?, ?, ?)
            """, (username, email, password_hash, name, role_id))

            conn.commit()
            admin_id = cur.lastrowid

        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()

        return jsonify({
            "message": "Admin user created successfully",
            "admin": {
                "user_id": admin_id,
                "username": username,
                "email": email,
                "name": name,
                "role": "admin"
            }
        }), 201


    """API to post a new user to the users table in database"""

    @app.route("/users/register", methods= ["POST"])
    def register_user():

        # Extract the user info from the JSON object sent by postman/frontend 
        data = request.get_json() or {} # if nothing sent

        # Validate required fields
        required_fields = ["username", "email", "password", "name"]
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
        forced_role = "user" #regular

        # Establish database connection
        conn = get_db_connection()
        try: 
            cur = conn.cursor()

            # Find the role ID of the role in roles table
            cur.execute(
                "SELECT role_id FROM roles WHERE role = ?", (forced_role,),)
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
                "role": forced_role

            }
        }), 201 # created

    """API to login an existing user"""

    @app.route("/users/login", methods= ["POST"])
    def login_user():
        data = request.get_json() or {}

        # Validate the input fields
        if "username" not in data or "password" not in data:
            return jsonify({"error": "Username and password are required to login."}), 400
        
        # Extract data
        username = data["username"].strip()
        password = data["password"]

        conn = get_db_connection()
        try:
            cur = conn.cursor()

            # Get the user by username, if exists
            cur.execute(
                """
                SELECT user_id, username, email, password_hash, role_id
                FROM users WHERE username = ?""", (username,),)
            user = cur.fetchone()

            # Check if user does not exist using username
            if user is None:
                return jsonify({"error": "Invalid username or password"}), 401
            
            # Check if the password is correct 
            password_match = check_password_hash(user["password_hash"], password)
            if not password_match:
                return jsonify({"error": "Invalid username or password"}), 401
            
            # If user exists, username and password are correct, fetch the role to authorize
            cur.execute("SELECT role FROM roles WHERE role_id = ?", (user["role_id"],)) 
            role_row = cur.fetchone() # returns a row with a role
            role = role_row["role"] if role_row else "unknown"

            # Block service_account login
            if role == "service_account":
                return jsonify({"error": "This account type cannot log in."}), 403

            # Create JWT token with the user_id, username, and role (for authorization)
            access_token = create_access_token(
                identity=str(user["user_id"]),
                additional_claims={
            "username": user["username"],
            "role": role
        }
)

        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()
        
        # Json response
        return jsonify ({
            "message": "Login successful",
            "token": access_token,
            "user": {
                "user_id": user["user_id"],
                "username": user["username"],
                "email": user["email"],
                "role": role
            }
        }), 200

    """API to allow all user types to read their own profile."""
    @app.route("/users/me", methods= ["GET"])
    @jwt_required()
    def get_my_profile():

        # Get the logged in user id and claims from token
        user_id = int(get_jwt_identity())  
        claims = get_jwt()                 
        role = claims["role"]


        conn = get_db_connection()
        try:
            cur = conn.cursor()

            # Fetch the user info by ID
            cur.execute(
                """
                SELECT u.user_id, u.username, u.email, u.name, r.role 
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                WHERE u.user_id =?
                """,
                (user_id,))
            
            user = cur.fetchone()
            
            if not user:
                return jsonify({"error": "User not found"}), 404

        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()

        # Success response
        return jsonify({
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"]
        }), 200



    """API to update own profile."""
    @app.route("/users/me", methods= ["PUT"])
    @jwt_required()

    def update_my_profile():
        user_id = int(get_jwt_identity())  
        claims = get_jwt()                 
        role = claims["role"]

        # Validate user type
        if role == "service_account":
            return jsonify({"error": "Service accounts cannot update profile"}), 403

        # Extraxt user profile data
        data = request.get_json() or {}
        allowed_fields = ["username", "email", "password", "name"]
        new_username = data.get("username")
        new_email = data.get("email")
        new_password = data.get("password")
        new_name = data.get("name")

        # If nothing is provided
        if not any([new_username, new_email, new_password, new_name]):
            return jsonify({"error": "No fields to update"}), 400
          
        conn = get_db_connection()
        try:
            cur = conn.cursor()

            # Get current user
            cur.execute(
                """
                SELECT * FROM users WHERE user_id = ?
                """,
                (user_id,)
            )
            current_user = cur.fetchone()

            if not current_user:
                return jsonify({"error": "User not found"}), 404
            
            # Set final values
            final_username = new_username.strip() if new_username else current_user["username"]
            final_email = new_email.strip() if new_email else current_user["email"]
            final_name = new_name.strip() if new_name else current_user["name"]
            final_password_hash = generate_password_hash(new_password) if new_password else current_user["password_hash"]

            # Verify uniqueness of username and email excluding current user
            cur.execute(
                    """
                    SELECT 1 FROM users WHERE (username =? OR email = ?) AND user_id !=?""" , 
                    (final_username, final_email, user_id),
                )
            if cur.fetchone():
                    return jsonify({"error": "Username or email already exists"}), 409 # conflict
                
            # Update the user
            cur.execute(
                """
                UPDATE users 
                SET username=?, email=?, password_hash =?, name=?  WHERE user_id = ?""",
                (final_username, final_email,  final_password_hash,final_name, user_id)
            )
            conn.commit()
        finally:
            conn.close()

        return jsonify({
        "message": "Profile updated successfully",
        "user": {
            "user_id": user_id,
            "username": final_username,
            "email": final_email,
            "name": final_name
        }
    }), 200


    """API to delete own account after password confirmation"""
    @app.route("/users/delete", methods= ["DELETE"])
    @jwt_required()

    def delete_my_profile():
        user_id = int(get_jwt_identity())  
        claims = get_jwt()                 
        role = claims["role"]
    
    
        # Validate user type
        if role == "service_account":
            return jsonify({"error": "Service accounts cannot delete their own profile"}), 403
        
        data = request.get_json() or {}
        password_confirm = data.get("password")

        if not password_confirm:
            return jsonify({"error": "Password confirmation is required"}), 400
        
        conn = get_db_connection()
        try:
            cur = conn.cursor()

            # Fetch password to compare 
            cur.execute(
                """
                SELECT password_hash FROM users WHERE user_id =?""",
                (user_id,)
            )

            password_row = cur.fetchone()
            if not password_row:
                return jsonify({"error": "User not found"}), 404
            
            password_hash = password_row["password_hash"]

            if not check_password_hash(password_hash, password_confirm):
                return jsonify({"error": "Incorrect password"}), 401
            
            # Cancel all active bookings upon deletion
            cur.execute(
                """
            UPDATE bookings
            SET status = 'cancelled'
            WHERE user_id =? AND status = 'confirmed' """,
            (user_id,) )

            # Remove all previous reviews 
            cur.execute(
                """
                DELETE FROM reviews WHERE user_id =? """,
                (user_id,)
            )

            # Delete user 
            cur.execute("""
                DELETE FROM users WHERE user_id = ?""",
                (user_id,))
            
            conn.commit()
    
        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()
        return jsonify({
                "message": "Account deleted successfully. All active bookings were cancelled, and all reviews were deleted.",
                "user_id_deleted": user_id
        }), 200   
    
    
    """Admin only API: assign roles"""
    @app.route("/users/<int:user_id>/role", methods= ["PUT"])
    @jwt_required()

    def assign_change_role(user_id):
        claims = get_jwt()                 
        role = claims["role"]

        # check if the user is authorized (admins only)
        if role != "admin":
            return jsonify({"error": "Only admins are authorized to check users' related information."}), 403
        
        # Extract new role
        data= request.get_json() or {}
        new_role = data.get("role")

        # Validate input 
        if not new_role:
            return jsonify({"Role is required"}), 400
        
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            
            # Check if the user exists 
            cur.execute(
                """
                SELECT * FROM users WHERE user_id =?
                """, (user_id,)
            )
            user = cur.fetchone()
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            # find the role ID for the new role
            cur.execute(
                """
                SELECT role_id FROM roles WHERE role =?""", 
                (new_role,))
            role_id_row = cur.fetchone()
            if not role_id_row:
                return jsonify({"error": "Invalid role"}), 400
            role_id = role_id_row["role_id"]

            # Update the user role
            cur.execute(
                """ 
                UPDATE users SET role_id = ? WHERE user_id =? """,
                (role_id, user_id)
            )

            conn.commit()
        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()
        return jsonify({
            "message": "Role updated successfully",
            "user": {
                "user_id": user_id,
                "new_role": new_role
            }
        }), 200

    

    """Admin only API: get all users"""
    @app.route("/users", methods= ["GET"])
    @jwt_required()

    def get_all_users():
        claims = get_jwt()                 
        role = claims["role"]

        # check if the user is authorized (admins only)
        if role != "admin":
            return jsonify({"error": "Only admins are authorized to check users' related information."}), 403
        
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT u.user_id, u.username, u.email, u.name, r.role
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                ORDER BY u.user_id ASC"""
            )

            users = cur.fetchall()

            # Response format 
            users_list = []
            for user in users:
                users_list.append({
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "email": user["email"],
                    "name": user["name"],
                    "role": user["role"]            
                })
        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()

        return jsonify({"users": users_list}), 200

    """Admin API: get a specific user's profile by username"""

    @app.route("/users/<string:username>", methods= ["GET"])
    @jwt_required()
    def get_user_by_username(username):
        claims = get_jwt()                 
        role = claims["role"]

        # check if the user is authorized (admins only)
        if role != "admin":
            return jsonify({"error": "Only admins are authorized to check users' related information."}), 403
        
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT u.user_id, u.username, u.email, u.name, r.role
                FROM users u 
                JOIN roles r ON u.role_id = r.role_id
                WHERE u.username =?""",
            (username,)
            )

            user = cur.fetchone()
            if not user:
                return jsonify({"error": "User not found"}), 404
            
        except sqlite3.Error as e:
            return jsonify({"error": f"Database error: {e}"}), 500
        finally:
            conn.close()   
        
        return jsonify({
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"]
    }), 200

    


    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5001, debug=True)

