"""
**Users Service - API Module**
    This module implements the Users microservice of the system. It manages user
    registration, authentication, authorization, role assignment, profile
    management, and administrative actions. The endpoints are exposed through a
    Flask Blueprint (``users_bp``) and integrated into the main application via
    ``create_app()``.

**Main Features**
    - User registration with hashed passwords.
    - JWT-based authentication and token generation.
    - Role-based access control (Admin, User, Auditor, Facility Manager,
Moderator, Service Account).
    - Profile viewing, updating, and deletion.
    - Administrative operations:
        - Initialize system roles.
        - Create the first admin account.
        - Assign or change roles for users.
        - Reset user passwords.
        - Delete user accounts.
    - Internal health check endpoint.

**Structure**
    - ``users_bp``: Flask Blueprint containing all Users API routes.
    - ``get_db_connection()``: Utility to create SQLite database connections with
    foreign key enforcement enabled.
    - ``create_app()``: Application factory configuring JWT and registering the
    users blueprint.

**Database Tables Used**
    - ``users`` - Stores user accounts and hashed passwords.
    - ``roles`` - Defines available system roles.
    - ``bookings`` - Used when deleting users to cancel active bookings.
    - ``reviews`` - Used when deleting users to remove authored reviews.

**Authentication**
    Most endpoints require a valid JWT access token. Required roles vary per
    operation (e.g., Admin-only, Admin/Auditor, or Any Authenticated User).

    This module is consumed by Sphinx to generate HTML documentation for all Users
    service endpoints.
"""
import pybreaker
from flask import Flask, jsonify, request
from flask import Blueprint
import requests
import sqlite3
import os
from .error_handlers import register_error_handlers
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask_jwt_extended import JWTManager, create_access_token
from datetime import timedelta
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address



# Connecting to the database 
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "project.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # To access columns by name
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn # connection object to run queries

users_bp = Blueprint("users_bp", __name__)
@users_bp.route("/version", methods=["GET"])
def get_version():
    return {"service": "users", "version": "v1"}, 200

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per minute"],
    storage_uri="memory://"
)

breaker = pybreaker.CircuitBreaker(
    fail_max=3,          # 3 consecutive failures triggers OPEN state
    reset_timeout=10     # after 10 seconds breaker goes HALF-OPEN
)

### API to check database connection
@users_bp.route("/health", methods=["GET"])
def health():
    """
    **Service health check endpoint.**

    - **URL:** ``/health``  
    - **Method:** ``GET``  
    - **Authentication:** None

    This endpoint is used to verify that the Users Service is running correctly and
    that the database connection is functioning. It performs a simple connectivity
    test by opening and closing a database connection.  

    A successful response indicates that both the service and the database are
    operational.

    **Behavior:**
        - Attempts to establish a connection to the SQLite database.
        - Closes the connection if successful.
        - Returns a JSON object with service and database status.

    **Responses:**
        - **200 OK** - Service is running and database connection succeeded.
        - **500 Internal Server Error** - Database connection failed.

    **Example Successful Response:**

        .. code-block:: json

            {
                "service": "users",
                "db": "connected",
                "status": "ok"
            }

    **Example Error Response:**

        .. code-block:: json

            {
                "service": "users",
                "db_error": "unable to open database file"
            }
    """

    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"service": "users", "db": "connected", "status": "ok"}), 200
    except Exception as e:
        return jsonify({"service": "users", "db_error": str(e)}), 500
        
### API to post user roles to the roles table in database
@users_bp.route("/roles/init", methods= ["POST"])
def init_roles():
    """
    Initialize default system roles.

    - **URL:** ``/roles/init``  
    - **Method:** ``POST``  
    - **Authentication:** None

    This endpoint inserts the predefined system roles into the ``roles`` table.
    If a role already exists, it is ignored to prevent duplication.  
    This endpoint is typically called once during system setup or deployment.

    **Roles Created:**
        - **admin** - System administrator  
        - **user** - Regular user  
        - **facility_manager** - Manages rooms and equipment  
        - **moderator** - Handles room reviews  
        - **auditor** - Read-only access for audits/logs  
        - **service_account** - Restricted non-human service-level account  

    **Behavior:**
        - Opens a database connection.
        - Iterates through the predefined roles list.
        - Uses ``INSERT OR IGNORE`` to avoid duplicate role creation.
        - Commits changes and closes the database connection.

    **Responses:**
        - **201 Created** - Roles successfully initialized (or already existed).
        - **500 Internal Server Error** - Database insert operation failed.

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Roles initialized (or already existed)."
            }
    """
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
    
### API to initialize the admim's profile to the database
@users_bp.route("/admin/init", methods=["POST"])
def init_admin():
    """
    Initialize the system's primary administrator account.

    - **URL:** ``/admin/init``  
    - **Method:** ``POST``  
    - **Authentication:** None

    This endpoint is used to create the first administrator account in the system.
    It should be executed only once, typically during system deployment.  
    If an admin already exists, the request is rejected to prevent multiple initial
    admin accounts from being created.

    **Request JSON Fields:**
        - **username** (*str*) – Admin's username (must be unique).  
        - **email** (*str*) – Admin's email address (must be unique).  
        - **password** (*str*) – Raw password (stored securely as a hash).  
        - **name** (*str*) – Full name of the administrator.

    **Behavior:**
        - Validates the presence of all required fields.
        - Checks whether an admin account already exists.
        - Retrieves the role ID for the ``admin`` role.
        - Ensures the username and email are unique across users.
        - Hashes the password using ``generate_password_hash``.
        - Inserts the new admin user into the database.
        - Returns the created admin's profile information.

    **Responses:**
        - **201 Created** - Admin successfully initialized.
        - **400 Bad Request** - Missing required field(s).
        - **403 Forbidden** - An admin already exists.
        - **409 Conflict** - Username or email already exists.
        - **500 Internal Server Error** - Database error or missing admin role.

    **Example Request:**

        .. code-block:: json

            {
                "username": "sysadmin",
                "email": "admin@example.com",
                "password": "securePass123",
                "name": "System Administrator"
            }

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Admin user created successfully",
                "admin": {
                    "user_id": 1,
                    "username": "sysadmin",
                    "email": "admin@example.com",
                    "name": "System Administrator",
                    "role": "admin"
                }
            }
    """

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


### API to post a new user to the users table in database
@users_bp.route("/users/register", methods= ["POST"])
@limiter.limit("10 per hour")
def register_user():
    """ 
    **Endpoint to register a new user**

    - **URL:** ``/users/register`` 
    - **Method:** ``POST`` 
    - **Authentication:** None
    
    This endpoint validates required fields (username, name, email, password). It then verifies the uniqueness of 
    username and email, hashes the password, and assigns a default regular user role. 
    It finally inserts the user's details under the users table in the database.    

    **Request JSON Fields:**
        - **username** (*str*) - Unique username.
        - **email** (*str*) - Unique email address.
        - **password** (*str*) - Raw password (stored as a hash).
        - **name** (*str*) - User's full name.

    **Behavior:**
        - Validates required fields.
        - Strips whitespace from textual fields  
        - Verifies uniqueness of ``username`` and ``email``
        - Hashes password using ``werkzeug.security``
        - Assigns a default role: ``user``

    **Responses:**
        - **201 Created** - User successfully registered.
        - **400 Bad Request** - One or more required fields are missing.
        - **409 Conflict** -  Username or email already exists.
        - **500 Internal Server Error** -  Database operation failed.

    **Example Request:**

    .. code-block:: json

        {
            "username": "ayasabra",
            "email": "ayasabra@users.com",
            "password": "aya123",
            "name": "Aya Sabra"
        }

    **Example Successful Response:**

    .. code-block:: json

        {
            "message": "User registered successfully",
            "user": {
                "user_id": 4,
                "username": "ayasabra",
                "email": "ayasabra@users.com",
                "name": "Aya Sabra",
                "role": "user"
            }
        }
    """

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

### API to login an existing user
@users_bp.route("/users/login", methods= ["POST"])
@limiter.limit("5 per minute")
def login_user():
    """
    **Endpoint to authenticate an existing user and return a JWT access token**

    - **URL:** ``/users/login`` 
    - **Method:** ``POST`` 
    - **Authentication:** None
    
    This endpoint validates the input of all required fields (username and password), verifies the existence of user
    by username and validates the password. It then fetches the user role to deny service account logins, 
    and finally issues a JWT access token containing the user's ID, and claims (username and role).

    **Request JSON Fields:**
        - **username** (*str*) - User's unique username.
        - **password** (*str*) - User's raw password.

    **Behavior:**
        - Validates the input of ``username`` and ``password``.
        - Fetches the user by username to verify existence.
        - Validate the password using ``werkzeug.security.check_password_hash``.
        - Fetches the user's role from the database to determine authorities.
        - Rejects ``service_account`` login requests.
        - Generates a JWT token including:
            - ``user_id`` (JWT identity)
            - ``username`` (claim)
            - ``role`` (claim)

    **Responses:**
        - **200 OK**- Login successful; JWT token returned.
        - **400 Bad Request** -  Username or password fields are missing.
        - **401 Unauthorized** - Invalid username or password.
        - **403 Forbidden**- ``service_account`` role is not allowed to log in.
        - **500 Internal Server Error** -  Database operation failed.

    **Example Request:**

    .. code-block:: json

        {
            "username": "ayasabra",
            "password": "aya123"
        }

    **Example Successful Response:**

    .. code-block:: json

        {
            "message": "Login successful",
            "token": "eyJhb...",
            "user": {
                "user_id": 4,
                "username": "ayasabra",
                "email": "ayasabra@users.com",
                "role": "user"
            }
        }
    """

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

### API to allow all user types to read their own profile.
@users_bp.route("/users/me", methods= ["GET"])
@jwt_required()
def get_my_profile():
    """
    Retrieve the authenticated user's profile.

    - **URL:** ``/users/me``  
    - **Method:** ``GET``  
    - **Authentication:** JWT required

    This endpoint extracts the user ID from the JWT token identity, and ensures the corresponsing
    user exists in the database. It then fetches the user information and returns their profile details 
    including ID, name, username, email, and role. 

    **Behavior:**
        - Extracts ``user_id`` and claims from the JWT token.  
        - Fetches the corresponding user from the database.  
        - Returns the user's profile information.  
        - Handles the case where the user record no longer exists.  

    **Responses:**

        - **200 OK** - Profile successfully retrieved.
        - **404 Not Found** - User does not exist.
        - **500 Internal Server Error** - Database error occurred.

    **Example Successful Response**

        .. code-block:: json

            {
                "user_id": 4,
                "username": "ayasabra",
                "email": "ayasabra@users.com",
                "name": "Aya Sabra",
                "role": "user"
            }
    """

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



### API to update own profile.
@users_bp.route("/users/me", methods= ["PUT"])
@jwt_required()

def update_my_profile():
    """
    Update the authenticated user's profile.

    **URL:** ``/users/me``  
    **Method:** ``PUT``  
    **Authentication:** JWT required

    This endpoint allows an authenticated user (except service accounts) to update their 
    own profile information. The final profile information reflect the new values for the 
    fields provided in the request body and the old values for the other fields. 
    Role change requests will be ignored by the system. 

    **Allowed but optional fields to be updated:**
        - **username** (*str*) - New username (must be unique).
        - **email** (*str*) - New email address (must be unique).
        - **password** (*str*) -  New password (stored as a hash).
        - **name** (*str*) - Updated full name.

    **Behavior:**
        - Extracts ``user_id`` from the JWT token.
        - Rejects profile updates for users with role ``service_account``.
        - Fetches the current user information from the database.
        - Ensures at least one field is provided in the JSON body.
        - Trims whitespace from provided fields.
        - Validates the uniqueness of the new ``username`` and ``email``.
        - Hashes the password using ``werkzeug.security.generate_password_hash``.
        - Updates the fields provided in the request only.
        - Ignores user role field updates.

    **Responses:**
        - **200 OK** - Profile updated successfully.
        - **400 Bad Request** - No fields were provided to update.
        - **403 Forbidden** - Service accounts cannot update their profiles.
        - **404 Not Found** - User does not exist.
        - **409 Conflict** - Username or email already exists.
        - **500 Internal Server Error** - Database error occurred.

    **Example Request:**

    .. code-block:: json

        {
            "username": "aya_sabra",
            "email": "aya_sabra@users.com",
            "password": "aya_123",
            "name": "Aya Sabra"
        }

    **Example Successful Response:**

    .. code-block:: json

        {
            "message": "Profile updated successfully",
            "user": {
                "user_id": 4,
                "username": "aya_sabra",
                "email": "aya_sabra@users.com",
                "name": "Aya Sabra"
            }
        }
    """

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


### API to delete own account after password confirmation
@users_bp.route("/users/delete", methods= ["DELETE"])
@jwt_required()

def delete_my_profile():
    """
    **Delete the authenticated user's account.**

    - **URL:** ``/users/delete``  
    - **Method:** ``DELETE``  
    - **Authentication:** JWT required

    This endpoint allows an authenticated user (except service accounts) to permanently 
    delete their account after password confirmation to avoid non-user or accidental requests. 
    Upon deletion, the user's active bookings are automatically cancelled and
    bookings reviews are removed. 

    **Request JSON Fields:**
        - **password** (*str*) - The user's current password.

    **Behavior:**
        - Extracts ``user_id`` from the identity and role from the claim of the JWT token.
        - Reject deletion requests from users with the role ``service_account``.
        - Validates that a password is provided for confirmation.
        - Fetches the user's stored password hash using ``werkzeug.security.check_password_hash``.
        - Verifies the provided password by comapring it to stored user's password.
        - Cancels all user's active (confirmed and pending) bookings.
        - Deletes all the user's bookings reviews.
        - Removes the user record from the database.

    **Responses:**
        - **200 OK** - Account deleted; active bookings cancelled; reviews removed.
        - **400 Bad Request** - Password confirmation not provided.
        - **401 Unauthorized** - Incorrect password.
        - **403 Forbidden** - Service accounts cannot delete themselves.
        - **404 Not Found** - User not found.
        - **500 Internal Server Error** - Database error occurred.

    **Example Request:**

        .. code-block:: json

            {
                "password": "aya_123"
            }

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Account deleted successfully. 
                All active bookings were cancelled, and all reviews were deleted.",
                "user_id_deleted": 4
            }
    """

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


### Admin only API: assign roles
@users_bp.route("/users/<int:user_id>/role", methods= ["PUT"])
@jwt_required()

def assign_change_role(user_id):
    """
    **Assign or change a user's role (admin-only API).**

    - **URL:** ``/users/<user_id>/role``  
    - **Method:** ``PUT``  
    - **Authentication:** JWT required  
    - **Authorization:** Admin only

    This endpoint allows the system admin to assign a role or change the role of an existing user.
    The admin provided a role from the ones already listed in the ``roles`` table im the database. 
    After verification of both the existence of the user and the role, teh user's role field is updated
    in the database,

    **Request JSON Fields:**
        - **role** (*str*) - The new user's role to be assigned (should exist in the ``roles`` table)

    **Behavior:**
        - Extracts the current user's role from the JWT claims.
        - Ensures the requester has the ``admin`` role.
        - Validates that the JSON body contains a ``role`` field.
        - Validates the existence of the target user.
        - Validates the existence of the new role in the database.
        - Finds the ID of the new role in the ``roles``.
        - Updates the user's ``role_id`` with the corresponding role ID.

    **Responses:**
        - **200 OK** - User role updated successfully.
        - **400 Bad Request** - Missing role field or invalid role name.
        - **403 Forbidden** - Non-admin users cannot modify roles.
        - **404 Not Found** - Target user not found.
        - **500 Internal Server Error** - Database error occurred.

    **Example Request:**

        .. code-block:: json

            {
                "role": "facility_manager"
            }

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Role updated successfully",
                "user": {
                    "user_id": 5,
                    "new_role": "facility_manager"
                }
            }
        """

    claims = get_jwt()                 
    role = claims["role"]

    # check if the user is authorized (admins only)
    if role != "admin":
        return jsonify({"error": "Only admins are authorized to modify users' related information."}), 403
    
    # Extract new role
    data= request.get_json() or {}
    new_role = data.get("role")

    # Validate input 
    if not new_role:
        return jsonify({"error":"Role is required"}), 400
    
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


### Admin only API: get all users
@users_bp.route("/users", methods= ["GET"])
@limiter.limit("20 per minute")
@jwt_required()

def get_all_users():

    """
    **Retrieve the list of all users (admin and auditor only).**

    - **URL:** ``/users``  
    - **Method:** ``GET``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin`` or ``auditor``

    This endpoint allows both the system administrator and the auditors to get all user information
    in a structured list. It rejects any other types of users from requesting users' information. 
    
    **Behavior:**
        - Extracts the user's role from the JWT claims.
        - Ensures that only ``admin`` or ``auditor`` roles can access the "get all users" endpoint.
        - Retrieves all users from the database, ordered by their ``user_id``.
        - Joins the ``users`` and ``roles`` tables on the ``role_id``  to retrieve the user role.
        - Returns a list of user objects inclusing their IDs, usernames, emails, names, and roles.

    **Response Fields (per user):**
        - **user_id** (*int*)
        - **username** (*str*)
        - **email** (*str*)
        - **name** (*str*)
        - **role** (*str*)

    **Responses:**
        - **200 OK** - Returns a list of all users.
        - **403 Forbidden** - User is not authorized to read all accounts.
        - **500 Internal Server Error**- Database query failed.

    **Example Successful Response:**

        .. code-block:: json

            {
                "users": [
                    {
                        "user_id": 1,
                        "username": "admin",
                        "email": "admin@users.com",
                        "name": "System Admin",
                        "role": "admin"
                    },
                    {
                        "user_id": 4,
                        "username": "aya_sabra",
                        "email": "aya_sabra@users.com",
                        "name": "Aya Sabra"
                        "role": "user"
                    }
                                        {
                        "user_id": 5,
                        "username": "imane_ghalayini",
                        "email": "imane_ghalayini@users.com",
                        "name": "Imane Ghalayini"
                        "role": "facility_manager"
                    }
                ]
            }
    """

    claims = get_jwt()                 
    role = claims["role"]

    # check if the user is authorized (admins only)
    if role not in["admin", "auditor"]:
        return jsonify({"error": "Not authorized."}), 403
    
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

### Admin API: get a specific user's profile by username
@users_bp.route("/username/<string:username>", methods= ["GET"])
@jwt_required()
def get_user_by_username(username):
    """
    **Retrieve a user's profile by username (admin and auditor only).**

    - **URL:** ``/username/<username>``  
    - **Method:** ``GET``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin`` or ``auditor``

    This endpoint allows both the system administrator and the auditors to 
    retrieve a user's profile by providing their username.  It rejects requests from
    users with any other roles. 

    **Behavior:**
        - Extracts the requester's role from the JWT token.
        - Ensures that only ``admin`` and ``auditor`` users have access.
        - Finds the user by the provided username if they
        - Joins the users and roles table on the ``role_id`` to retrieve the user role.
        - Returns the user's profile details 

    **Response Fields:**
        - **user_id** (*int*)
        - **username** (*str*)
        - **email** (*str*)
        - **name** (*str*)
        - **role** (*str*)

    **Responses:**
        - **200 OK** - User profile successfully retrieved.
        - **403 Forbidden** - Requester does not have permission.
        - **404 Not Found** - No user exists with the given username.
        - **500 Internal Server Error** - Database query failed.

    **Example Successful Response:**

        .. code-block:: json

            {
                "user_id": 4,
                "username": "aya_sabra",
                "email": "aya_sabra@users.com",
                "name": "Aya Sabra",
                "role": "user"
            }
    """
    claims = get_jwt()                 
    role = claims["role"]

    # check if the user is authorized (admins only)
    if role not in ["admin", "auditor"]:
        return jsonify({"error": "Not authorized."}), 403
    
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

### Admin API: reset a user's password
@users_bp.route("/users/<int:user_id>/reset-password", methods=["PUT"])
@jwt_required()

def reset_password(user_id):
    """
    **Reset a user's password (admin only).**

    - **URL:** ``/users/<user_id>/reset-password``  
    - **Method:** ``PUT``  
    - **Authentication:** JWT required  
    - **Authorization:** Admin only

    This endpoint allows the system administrator to reset the password of any user in the
    system. The admin should provide a new password in the request body. The new password
    is then and hashed and assigned to the user. 

    **Request JSON Fields:**
        - **password** (*str*) - The new password to be assigned to the user.

    **Behavior:**
        - Extracts the requester's role from the JWT token.
        - Ensures that only users with the ``admin`` role have access to this endpoint.
        - Validates that a new password is provided in the request body.
        - Validates the existence of teh target user in the database.
        - Hashes the new password using ``werkzeug.security.generate_password_hash``.
        - Replaces the user's password in the ``users`` table with the new password.

    **Responses:**
        - **200 OK** - Password reset successfully.
        - **400 Bad Request** - Missing new password field.
        - **403 Forbidden** - Non-admin users cannot reset passwords.
        - **404 Not Found** - Target user does not exist.
        - **500 Internal Server Error** - Database operation failed.

    **Example Request:**

        .. code-block:: json

            {
                "password": "reset_012"
            }

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Password reset successfully.",
                "user_id": 3
            }
    """

    claims = get_jwt()                 
    role = claims["role"]

    # check if the user is authorized (admins only)
    if role != "admin":
        return jsonify({"error": "Only admins can reset passwords."}), 403
    
    # Extract new password
    data = request.get_json()
    new_password = data.get("password")

    if not new_password:
        return jsonify({"error": "New password is required."}), 400

    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Check if the user exists
        cur.execute(
            """ SELECT user_id FROM users where user_id =?""",
            (user_id,)
        )
        user = cur.fetchone()
        
        if not user:
            return jsonify({"error": "User not found."}), 404
        
        # Hash the new password
        new_password_hash = generate_password_hash(new_password)

        # Update the user's password
        cur.execute(
            """
            UPDATE users SET password_hash=? WHERE user_id =?""",
            (new_password_hash, user_id)
        )

        conn.commit()

    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        conn.close()

    return jsonify({
        "message": "Password reset successfully.",
        "user_id": user_id
    }), 200  

### Admin only API: delete a user's account by ID
@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
@jwt_required()

def delete_user(user_id):
    """
    **Delete a user's account by ID (admin only API).**

    - **URL:** ``/users/<user_id>``  
    - **Method:** ``DELETE``  
    - **Authentication:** JWT required  
    - **Authorization:** Admin only

    This endpoint premits the system administrator to delete a user account from the
    system. It cancels all user's active bookings (confimed and pending) and
    delete the user's previous bookings reviews. Finally, it deletes the user's account by 
    removing it from the users table in the database.
    Administrators are not allowed to delete their own accounts.

    **Behavior:**
        - Extracts the admin's ID and role from the JWT token.
        - Ensures that only admins are granted access to this endpoint.
        - Blocks admins from deleting their own accounts.
        - Confirms the existence of the intended user in the database.
        - Cancels all user's active(``confirmed``, and ``pending``) bookings.
        - Removes the user record from the ``users`` table in the database.

    **Responses:**
        - **200 OK** - User deleted successfully.
        - **400 Bad Request** - Admin attempted to delete their own account.
        - **403 Forbidden** - Non-admin users cannot delete accounts.
        - **404 Not Found** - User does not exist.
        - **500 Internal Server Error** - Database error occurred.

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "User deleted successfully.",
                "user_id_deleted": 3
            }
    """

    admin_id = int(get_jwt_identity())
    claims = get_jwt()                 
    role = claims["role"]

    # check if the user is authorized (admins only)
    if role != "admin":
        return jsonify({"error": "Only admins can delete users."}), 403
    
    # Reject the admin's request to delete their own account
    if admin_id == user_id:
        return jsonify({"error": "Admins cannot delete their own account."}), 400
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Check if user exists
        cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        user = cur.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Cancel the active bookings
        cur.execute(
            """
            UPDATE bookings
            SET status = 'cancelled'
            WHERE user_id =? AND status = 'confirmed' """,
            (user_id,))
        
        # Delete the user
        cur.execute(
            """
            DELETE FROM users WHERE user_id =?""",
            (user_id,)
        )
        
        conn.commit()

    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        conn.close()

    return jsonify({
        "message": "User deleted successfully.",
        "user_id_deleted": user_id
    }), 200

### Cicuit breaker 
@users_bp.route("/rooms/check", methods=["GET"])
def check_rooms_service():
    """
    Test endpoint using Circuit Breaker to check Rooms Service availability.
    - If Rooms Service fails 3 times → breaker opens (fast-fail mode)
    - After 10 seconds → breaker half-open
    - If next request succeeds → breaker closes again
    """
    try:
        response = breaker.call(
            requests.get,
            "http://127.0.0.1:5002/rooms/health",
            timeout=2
        )

        if response.status_code == 200:
            return jsonify({
                "service": "users",
                "rooms_service": "reachable",
                "rooms_response": response.json()
            }), 200

        return jsonify({
            "service": "users",
            "rooms_service": "unhealthy",
            "status": response.status_code
        }), 500

    except pybreaker.CircuitBreakerError:
        # The breaker is OPEN: fast failure
        return jsonify({
            "service": "users",
            "rooms_service": "circuit_open",
            "message": "Circuit breaker is OPEN — too many recent failures."
        }), 503

    except Exception as e:
        return jsonify({
            "service": "users",
            "rooms_service": "down",
            "error": str(e)
        }), 500


    
def create_app():
    app = Flask(__name__)

    limiter.init_app(app)
    app.config["JWT_SECRET_KEY"] = "secret_key"   
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1) # The token expires in one hour
    jwt = JWTManager(app)
    app.register_blueprint(users_bp)
    register_error_handlers(app)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5001, debug=True)

