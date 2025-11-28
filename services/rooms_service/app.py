"""
**Rooms Service - API Module**
    This module implements the Rooms microservice responsible for managing rooms,
    their equipment, availability status, and search/filter operations. All
    endpoints are organized under the ``rooms_bp`` Flask Blueprint.

**Main Features**
    - Create, update, view, and delete rooms.
    - Manage room equipment (add, remove, increment, decrement).
    - Update room operational status (available / out_of_service).
    - Retrieve rooms with flexible filtering (capacity, location, status,
    equipment).
    - Health check endpoint.

**Structure**
    - ``rooms_bp``: Flask Blueprint containing all Rooms API routes.
    - ``get_db_connection()``: Imported utility for SQLite connections.
    - Routes include:
        - POST ``/rooms`` - Create a room.
        - GET ``/rooms`` - Retrieve rooms (with filters).
        - GET ``/rooms/<id>`` - Get room details.
        - PUT ``/rooms/<id>`` - Update room information.
        - DELETE ``/rooms/<id>`` - Delete a room and related records.
        - POST/DELETE equipment routes.
        - PUT room status route.
        - GET ``/rooms/health`` - Service health check.

**Database Tables Used**
    - ``rooms`` - Main room definitions.
    - ``equipment`` - Global equipment definitions.
    - ``room_equipment`` - Room-to-equipment mapping table.
    - ``bookings`` - Active bookings cancelled when a room is deleted.
    - ``reviews`` - Reviews removed when a room is deleted.

**Authentication & Authorization**
    All endpoints require JWT-based authentication. Only privileged roles
    (``admin`` or ``facility_manager``) may create, modify, or delete rooms or
    equipment. Other roles (``user``, ``auditor``) may retrieve room details.

    This docstring is used by Sphinx to generate top-level HTML documentation for
    the entire Rooms microservice.
"""

from flask import Flask, jsonify, request, Blueprint
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
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "database", "project.db")
DB_PATH = os.environ.get("DB_PATH", DEFAULT_DB_PATH)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # To access columns by name
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

rooms_bp = Blueprint("rooms_bp", __name__)

@rooms_bp.route("/health", methods=["GET"])
def health():
    """
    Health check endpoint for the Rooms service.

    **URL:** ``/rooms/health``  
    **Method:** ``GET``  
    **Authentication:** None

    This endpoint is used to verify that the Rooms service is running and
    responding correctly.  
    It does not perform any database checks—only returns a simple JSON status
    message confirming service availability.

    **Responses:**
    - **200 OK** – Rooms service is responsive.

    **Example Successful Response:**

    .. code-block:: json

        {
            "service": "rooms",
            "status": "ok"
        }
    """

    return jsonify({"service": "rooms", "status": "ok"}), 200

### API to create a new room
@rooms_bp.route("/rooms", methods=["POST"]) 
@jwt_required()
def create_room():
    """
    Create a new room (admin and facility manager only).

    - **URL:** ``/rooms``  
    - **Method:** ``POST``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin`` or ``facility_manager``

    This endpoint allows users with user roles ``admin`` or ``facility_manager`` 
    to create a new room record in ``rooms`` table of the database. Each room creation
    request should include the room's name, capacity, location, and an optional equipment list.
    Each equipment item will be linked to an existing equipment type or added as a new one.
    All rooms are marked by default as available upon creation. 

    **Request JSON Fields:**
        - **name** (*str*) - Room name (required).  
        - **capacity** (*int*) - Capacity (required).  
        - **location** (*str*) - Room location (required).  
        - **equipment** (*list[str]*) - List of equipment (optional).

    **Behavior:**
        - Verifies that the requester has either ``admin`` or ``facility_manager`` roles.
        - Ensures that the required fields (``name``, ``capacity``, and ``location``) are provided in the request body.
        - Inserts the room into the ``rooms`` table with the default status ``available``.
        - For each provided equipment item:
            - Checks whether this type of equipment exists in the ``equipment`` table.
            - Inserts the new equipment type if it does not exist.
            - Creates a mapping in ``room_equipment`` with a default quantity of 1.
            - Returns the created room details.

    **Responses:**
        - **201 Created** - Room successfully created.
        - **400 Bad Request** - Missing required fields.
        - **403 Forbidden** - Requester is not authorized.
        - **500 Internal Server Error** - Database error occurred.

    **Example Request:**
        .. code-block:: json

            {
                "name": "Meeting room",
                "capacity": 25,
                "location": "Bechtel 300",
                "equipment": ["Projector", "Whiteboard", "Microphone"]
            }

    **Example Successful Response:**
        .. code-block:: json

            {
                "message": "Room created successfully",
                "room": {
                    "room_id": 2,
                    "name": "Meeting Room",
                    "capacity": 25,
                    "location": "Bechtel 300",
                    "status": "available",
                    "equipment": ["Projector", "Whiteboard", "Microphone"]
                    }
            }
    """

    claims = get_jwt()
    role = claims.get("role")   # FIXED

    # Validate authorization
    if role not in ["admin", "facility_manager"]:
        return jsonify({"error": "Not authorized to create rooms"}), 403
    
    # Extract data
    data = request.get_json() or {}
    name = data.get("name")
    capacity = data.get("capacity")
    location = data.get("location")
    equipment_list = data.get("equipment", []) or []
    default_status = "available"

    # Validate required fields
    if not name or not capacity or not location:
        return jsonify({"error": "Missing required fields: name, capacity, location"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Insert room
        cursor.execute(
            """
            INSERT INTO rooms (name, capacity, location, status)
            VALUES (?, ?, ?, ?)
            """,
            (name, capacity, location, default_status)
        )
        conn.commit()
        room_id = cursor.lastrowid

        # Insert equipment if any
        for equi in equipment_list:
            equi_type = equi.strip()

            # Check if equipment already exists
            cursor.execute("SELECT equi_id FROM equipment WHERE type = ?", (equi_type,))
            equi_row = cursor.fetchone()

            if equi_row:
                equi_id = equi_row["equi_id"]
            else:
                # Insert new equipment type (FIXED SQL)
                cursor.execute(
                    "INSERT INTO equipment (type) VALUES (?)",
                    (equi_type,)
                )
                conn.commit()
                equi_id = cursor.lastrowid

            # Insert into room_equipment
            cursor.execute(
                """
                INSERT INTO room_equipment (room_id, equi_id, quantity) 
                VALUES (?, ?, ?)
                """,
                (room_id, equi_id, 1)
            )
        
        conn.commit()

    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        conn.close()

    return jsonify({
        "message": "Room created successfully",
        "room": {
            "room_id": room_id,
            "name": name,
            "capacity": capacity,
            "location": location,
            "status": default_status,
            "equipment": equipment_list
        }
    }), 201


### API to get room details by ID
@rooms_bp.route("/rooms/<int:room_id>", methods=["GET"]) 
@jwt_required()
def get_room_by_id(room_id):
    """
    **Retrieve full details of a specific room by ID**

    - **URL:** ``/rooms/<room_id>``  
    - **Method:** ``GET``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin``, ``facility_manager``, ``auditor``, or ``user``

    This endpoint return the full details of a specific room upon request from 
    an authorized user. The details include the room's name, capacity, location,
    list of equipment along with the available quantity of each, and status 
    (available, booked, out of service).

    **Behavior:**
        - Extracts the user's role form the claims of the JWT toke.
        - Ensures that the user is authorized to request room details.
        - Fetches the room details by ID from the rooms table in the database.
        - Selects the IDs of the equipments assigned to the room from the 
        joined room_equipment table.
        - Tracks the quantity of each assigned equipment.
        - Returns a room object with its full details and current status.

    **Response Fields:**
        - **room_id** (*int*)
        - **name** (*str*)
        - **capacity** (*int*)
        - **location** (*str*)
        - **status** (*str*) - ``available``, ``booked``, or ``out_of_service``
        - **equipment** (*list*) - A list of objects:
            - **type** (*str*) - Equipment type  
            - **quantity** (*int*) - Available quantity  

    **Responses:**
        - **200 OK** - Room details returned successfully.
        - **403 Forbidden** - Requester is not authorized.
        - **404 Not Found** - Room does not exist.
        - **500 Internal Server Error** - Database error occurred.

    **Example Successful Response:**
        .. code-block:: json

            {
                "room_id": 4,
                "name": "Exam Room, C",
                "capacity": 50,
                "location": "SRB building, floor 3",
                "status": "booked",
                "equipment": [
                    {"type": "Computers", "quantity": 50},
                    {"type": "Whiteboard", "quantity": 1}
                ]
            }
    """

    claims = get_jwt()
    role = claims["role"]

    # Validate authorization
    authorized_roles = ["admin","facility_manager", "auditor", "user"]
    if role not in authorized_roles:
        return jsonify({"error": "Not authorized to view room details"}), 403
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Fetch details - equipment
        cur.execute(
            """
            SELECT room_id, name, capacity, location, status 
            FROM rooms
            WHERE room_id = ?
            """,
            (room_id,)
        )
        room = cur.fetchone()
        if not room:
            return jsonify({"error": "Room not found"}), 404
        
        # Fetch equipment list
        # loop in room_equipment table and for every row when the room_id = intended room_id, select from quipment table the corresponding item type to the equi_id in the room_equi table row 
        cur.execute(
            """
            SELECT e.type, re.quantity
            from equipment e
            JOIN room_equipment re ON e.equi_id = re.equi_id
            WHERE re.room_id = ?""",
            (room_id,)
        )
        equipment_rows = cur.fetchall()
        equipment_list = []
        for row in equipment_rows:
            equipment_list.append({
                "type": row["type"],
                "quantity": row["quantity"]
            })


    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        conn.close()

    return jsonify({
        "room_id": room["room_id"],
        "name": room["name"],
        "capacity": room["capacity"],
        "location": room["location"],
        "status": room["status"],
        "equipment": equipment_list
    }), 200


### API to edit room details: name, capacity, location
@rooms_bp.route("/rooms/<int:room_id>", methods=["PUT"]) 
@jwt_required()
def update_room_details(room_id):
    """
    Update room details (name, capacity, location)

    - **URL:** ``/rooms/<room_id>``  
    - **Method:** ``PUT``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin`` or ``facility_manager``

    This endpoints allows authorized users (``admin`` and ``facility_manager``)
    to update the name, the capacity, and the location of an existing room.
    It verifies that at least one field is provided in the request body and return 
    the room details with the new values for the updated fields and the old values for
    the other fields. Status and equipment update requests are ignored.

    **Updatable Fields (optional):**
        - **name** (*str*) -  New name.  
        - **capacity** (*int*) - New capacity.  
        - **location** (*str*) - New location.
    
    **Behavior:**
        - Extracts the user role from the claims of the JWT token. 
        - Ensures that the user is authorized to update room details. 
        - Rejects update request from non authorized users.
        - Ensures that at least one update field is provided in the request body.
        - Extracts the new field values from the request body.
        - Fetch the current room details from the databse, if the room exists.
        - Decides on the final room details by assigning the new values to the requested fields and the old values for the fields not included in the request.
        - Updates the room details in the database using the final values. 

    
    **Responses:**
        - **200 OK** - Room updated successfully.
        - **400 Bad Request** - No fields provided to update.
        - **403 Forbidden** - Requester is not allowed to update rooms.
        - **404 Not Found** - Room does not exist.
        - **500 Internal Server Error** - Database update failed.

    **Example Request:**
        .. code-block:: json

            {
                "name": "Conference Room",
                "capacity": 40,
                "location": "Bechtel, floor 3"
            }

    **Example Successful Response:**
        .. code-block:: json

            {
                "message": "Room updated successfully",
                "room": {
                    "room_id": 2,
                    "name": "Conference Room",
                    "capacity": 40,
                    "location": "Bechtel, floor 3",
                    "status": "out_of_service!"
                }
            }

    """

    claims = get_jwt()
    role = claims["role"]

    if role not in ["admin", "facility_manager"]:
        return jsonify({"error": "Not authorized to update room details"}), 403
        
    # Extract update fields
    data = request.get_json() or {}
    new_name = data.get("name")
    new_capacity = data.get("capacity")
    new_location = data.get("location")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Fetch the current fields of the room to be updated 
        cur.execute("""
            SELECT name, capacity, location, status 
            FROM rooms 
            WHERE room_id = ?
        """, (room_id,))
        
        room = cur.fetchone()

        if not room:
            return jsonify({"error": "Room not found"}), 404

        if not any([new_name, new_capacity, new_location]):
            return jsonify({"error": "No fields to update"}), 400


        
        # Determine the final fields of the room 
        final_name = new_name.strip() if new_name else room["name"]
        final_capacity = new_capacity if new_capacity else room["capacity"]
        final_location = new_location.strip() if new_location else room["location"]

        # Update room
        cur.execute("""
            UPDATE rooms
            SET name=?, capacity=?, location=?
            WHERE room_id = ?
        """, (final_name, final_capacity, final_location, room_id))

        conn.commit()

    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        conn.close()

    return jsonify({
        "message": "Room updated successfully",
        "room": {
            "room_id": room_id,
            "name": final_name,
            "capacity": final_capacity,
            "location": final_location,
            "status": room["status"]
        }
    }), 200


### API to delete a room with bookings cancellation and reviews removal
@rooms_bp.route("/rooms/<int:room_id>", methods=["DELETE"])
@jwt_required()
def delete_room(room_id):
    """
    **Delete an existing room and related data.**

    - **URL:** ``/rooms/<room_id>``  
    - **Method:** ``DELETE``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin`` or ``facility_manager``

    This endpoint cancels the intended room's pending and confirmed booking, 
    deletes related booking reviews, and removes all assigned equipments. Finally,
    it safely deletes the room record room from the rooms table in the database. 

    **Behavior:**
        - Verifies requester role (admin or facility manager).
        - Checks whether the room exists in the database.
        - Cancels all room bookings with status ``pending`` or ``confirmed``.
        - Deletes all reviews associated with the room.
        - Deletes all equipment mappings from ``room_equipment``.
        - Removes the room record from ``rooms`` table.
        - Returns a confirmation message with the deleted room ID.

    **Responses:**
        - **200 OK** - Room deleted successfully.
        - **403 Forbidden** - Requester is not authorized.
        - **404 Not Found** - Room does not exist.
        - **500 Internal Server Error** - Database operation failed.

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Room deleted successfully",
                "room_id_deleted": 13
            }
    """

    claims = get_jwt()
    role = claims["role"]

    if role not in ["admin", "facility_manager"]:
        return jsonify({"error": "Not authorized to update room details"}), 403
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Check if the room exists
        cur.execute(
            """
            SELECT room_id FROM rooms WHERE room_id =?""", 
            (room_id,)
        )
        room = cur.fetchone()
        if not room:
            return jsonify({"error": "Room not found"}), 404

        # Cancel active and pending bookings
        cur.execute(
            """
            UPDATE bookings 
            SET status = 'cancelled'
            WHERE room_id =? AND (status = 'pending' or status = 'confirmed') """,
            (room_id, )
        )

        # Delete all reviews
        cur.execute(
            """
        DELETE FROM reviews WHERE room_id =?""",
        (room_id,)
        )
        
        # Delete the room's equipment 
        cur.execute(
            """
            DELETE FROM room_equipment WHERE room_id =?""",
            (room_id,)
        )

        # Delete the room 
        cur.execute(
            """
            DELETE FROM rooms WHERE room_id=?""",
            (room_id,)
        )

        conn.commit()
    
    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        conn.close()

    return jsonify({
        "message": "Room deleted successfully",
        "room_id_deleted": room_id
    }), 200


### API to add a room equipment
@rooms_bp.route("/rooms/<int:room_id>/equipment", methods=["POST"])
@jwt_required()
def add_equipment(room_id):

    """
    **Add or increment an equipment item for a specific room.**

    - **URL:** ``/rooms/<room_id>/equipment``  
    - **Method:** ``POST``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin`` or ``facility_manager``

    This endpoint allows adding an equipment item to a room by an authorized user, while
    requests from unauthorized users are rejected. If the equipment type does not previously 
    exist in the global ``equipment`` table, it is automatically created. If the room already contains this equipment type,
    its quantity is incremented; otherwise, a new association entry is added in  
    ``room_equipment``.

    **Request JSON Fields:**
        - **equipment** (*str*) - The type/name of the equipment item to add.

    **Behavior:**
        - Verifies requester authorization.
        - Ensures that the intended room exist in the rooms table.
        - Posts the equipment type if it does not exist in the equipments table.
        - Checks whether the room already has this equipment:
            - If it does, increments its quantity.
            - If it does not, create the equipment type and add it to the room with quanity = 1.

    **Responses:**
        - **201 Created** - Equipment added or quantity incremented.
        - **400 Bad Request** - Missing equipment field.
        - **403 Forbidden** - Unauthorized requester.
        - **404 Not Found** - Room does not exist.
        - **500 Internal Server Error** - Database error.

    **Example Request:**

        .. code-block:: json

            {
                "equipment": "Whiteboard"
            }

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Equipment added successfully",
                "room_id": 10,
                "added_equipment": "Computer"
            }
    """

    claims = get_jwt()
    role = claims["role"]

    if role not in ["admin", "facility_manager"]:
        return jsonify({"error": "Not authorized to add room equipment"}), 403
    
    data = request.get_json() or {}
    equi_type = data.get("equipment")

    if not equi_type:
        return jsonify({"error": "Type of equipment item is required"}), 400
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Check if the room exists
        cur.execute(
            """
            SELECT room_id FROM rooms WHERE room_id =?
            """, (room_id,)
        )
        room_row = cur.fetchone()
        if not room_row:
            return jsonify({"error": "Room not found"}), 404
        
        # if the equipment type does not exist, add it
        cur.execute(
            """
            SELECT equi_id FROM equipment WHERE type =?""",
            (equi_type,)
        )
        equi_id_row = cur.fetchone()
        if equi_id_row:
            equi_id = equi_id_row["equi_id"]

        else:
            # add the new type 
            cur.execute(
                """
            INSERT INTO equipment (type) VALUES (?)""",
            (equi_type,)
            )
            equi_id = cur.lastrowid
        # Check if the room already has this equi type => increment quantity
        cur.execute(
            """
        SELECT quantity FROM room_equipment WHERE room_id =? AND equi_id = ?""",
        (room_id, equi_id)
        )
        quantity_row = cur.fetchone() 
        if quantity_row:
            quantity = quantity_row["quantity"]
        else:
            quantity = 0

        if quantity > 0 :
            # Increment 
            cur.execute(
                """
                UPDATE room_equipment 
                SET quantity = ?
                WHERE room_id =? AND equi_id =?""",
                (quantity + 1, room_id, equi_id)
            )
        else:
            # add the new item to the room
            cur.execute(
                """
                INSERT INTO room_equipment (room_id, equi_id, quantity)
                VALUES (?, ?, 1)""",
                (room_id, equi_id)
            )
        conn.commit()

    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        conn.close()

    return jsonify({
        "message": "Equipment added successfully",
        "room_id": room_id,
        "added_equipment": equi_type
    }), 201


### API to delete a room equipment
@rooms_bp.route("/rooms/<int:room_id>/equipment/<int:equi_id>", methods=["DELETE"])
@jwt_required()
def delete_equipment(room_id, equi_id):

    """
    **Remove or decrement an equipment item from a room.**

        - **URL:** ``/rooms/<room_id>/equipment/<equi_id>``  
        - **Method:** ``DELETE``  
        - **Authentication:** JWT required  
        - **Authorization:** ``admin`` or ``facility_manager``

    This endpoint removes equipment from a room.  
    If the equipment has a quantity greater than 1, the quantity is decremented.
    If the quantity is exactly 1, the equipment mapping is removed from
    ``room_equipment`` entirely.  
    The equipment type itself remains in the  ``equipment`` table.

    **Behavior:**
        - Verifies requester authorization.
        - Ensures the room exists.
        - Ensures the equipment type exists.
        - Ensures the equipment is actually assigned to the room.
        - Decrements quantity or deletes the mapping entirely.
        - Returns the equipment type removed.

    **Responses:**
        - **201 Created** - Equipment successfully removed or quantity decremented.
        - **403 Forbidden** - Unauthorized requester.
        - **404 Not Found** - Room or equipment not found, or equipment not assigned to the room.
        - **500 Internal Server Error** - Database failure.

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Equipment removed successfully",
                "room_id": 9,
                "removed_equipment": "Table"
            }
    """

    claims = get_jwt()
    role = claims["role"]

    if role not in ["admin", "facility_manager"]:
        return jsonify({"error": "Not authorized to delete room equipment"}), 403
            
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Check if the room exists
        cur.execute(
            """
            SELECT room_id FROM rooms WHERE room_id =?
            """, (room_id,)
        )
        room_row = cur.fetchone()
        if not room_row:
            return jsonify({"error": "Room not found"}), 404
        
        # if the equipment does not exists - cannot delete it
        cur.execute(
            """
            SELECT equi_id, type FROM equipment WHERE equi_id =?""",
            (equi_id,)
        )
        equi_id_row = cur.fetchone()
        if not equi_id_row:
            return jsonify({"error": "Equipment not found"}), 404
        
        equi_type = equi_id_row["type"]

        # Check if the room already has this equipment type => decrement quantity
        cur.execute(
            """
        SELECT quantity 
        FROM room_equipment 
        WHERE room_id =? AND equi_id = ?""",
        (room_id, equi_id)
        )
        quantity_row = cur.fetchone() 
        if not quantity_row:
            return jsonify({
            "error": "This equipment is not available in this room"
        }), 404

        quantity = quantity_row["quantity"] 

        if quantity > 1:
            # decrement 
            cur.execute(
                """
                UPDATE room_equipment 
                SET quantity = ?
                WHERE room_id =? AND equi_id =?""",
                (quantity - 1, room_id, equi_id)
            )
        else:
            # remove the equipment from the room
            cur.execute(
                """
                DELETE FROM room_equipment 
                WHERE room_id =? AND equi_id=?""",
                (room_id, equi_id)
            )
        conn.commit()

    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        conn.close()

    return jsonify({
        "message": "Equipment removed successfully",
        "room_id": room_id,
        "removed_equipment": equi_type
    }), 201

### API to mark a room out of service/available again
@rooms_bp.route("/rooms/<int:room_id>/status", methods =["PUT"])
@jwt_required()
def update_room_status(room_id):

    """
    **Update the availability status of a room.**

    - **URL:** ``/rooms/<room_id>/status``  
    - **Method:** ``PUT``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin`` or ``facility_manager``

    This endpoint allows the facility manager to marks a room out of service to temporarly
    prevent booking and mark it back as available when maintenance/safety issues resolution ..
    are complete. As a backup plan for when the facility manager is unavailable, 
    the admin is granted access to this endpoint as well. 

    **Status Values:**
        - ``available``
        - ``out_of_service``

    **Behavior:**
        - Extract the user role from the JWT token.
        - Ensure that only facility managers and admin are allowed access.
        - Validate a new status is provided and ensure it is one of (available, out_of_service).
        - Extract new status from the JSON request body.
        - Update the corresponsing room status to the new one.
     
    **Responses:**
        - **200 OK** - Status updated successfully.
        - **400 Bad Request** - Missing or invalid status.
        - **403 Forbidden** - Requester not authorized.
        - **500 Internal Server Error** - Database error.

    **Example Request:**

        .. code-block:: json

            {
                "status": "out_of_service"
            }

    **Example Successful Response:**

        .. code-block:: json

            {
                "message": "Room status updated successfully",
                "room_id": 8,
                "room_status": "out_of_service"
            }
    """

    claims = get_jwt()
    role = claims["role"]

    # Only admins and facility managers can mark a room out of service, and mark it back as available
    if role not in ["admin", "facility_manager"]:
        return jsonify({"error": "Not authorized to update room status"}), 403
    
    # Extract new status
    data = request.get_json() or {}
    new_status = data.get("status")

    if not new_status:
        return jsonify({"error": "New status is required"}), 400
    
    if new_status not in ["available", "out_of_service"]:
        return jsonify({"error": "Invalid status"}), 400
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE rooms
            SET status =? WHERE room_id =?""",
            (new_status, room_id)
        )
        conn.commit()

    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        conn.close()

    return jsonify({
        "message": "Room status updated successfully",
        "room_id": room_id,
        "room_status": new_status
    }), 200


### API to get all rooms with filters
@rooms_bp.route("/rooms", methods =["GET"])
@jwt_required()
def get_rooms():
    """
    **Retrieve a list of rooms with optional filtering.**

    - **URL:** ``/rooms``  
    - **Method:** ``GET``  
    - **Authentication:** JWT required  
    - **Authorization:** ``admin``, ``facility_manager``, ``user``, ``auditor``

    This endpoints allows users to view all available removes. 
    They can optionally filter out rooms by availability, by capacity, 
    by location, and by eqipment item available in their equipment list. 


    **Query Parameters:**
        - **capacity** (*int*, optional) - Minimum capacity of the room.  
        - **location** (*str*, optional) - Partial match filter using SQL ``LIKE``.  
        - **equipment** (*str*, optional) - Returns only rooms containing the specified equipment type.  
        - **status** (*str*, optional) - Filter by room status (``available``, ``booked``, ``out_of_service``).

    **Behavior:**
        - Validates user authorization.
        - Dynamically builds SQL query based on provided filters.
        - Supports combined filtering (e.g., capacity + location + equipment).
        - Returns each room along with its equipment list and quantities.

    **Responses:**
        - **200 OK** - Matching rooms returned successfully.
        - **403 Forbidden** - User not authorized to view rooms.
        - **500 Internal Server Error** - Database operation failed.

    **Example Request (with filters):**

        ``http://localhost:5000/rooms?capacity=20&location=Hall&equipment=Projector``

    **Example Successful Response:**

        .. code-block:: json

            {
                "rooms": [
                    {
                        "room_id": 5,
                        "name": "Main Conference Room",
                        "capacity": 30,
                        "location": "East Hall",
                        "status": "available",
                        "equipment": [
                            {"type": "Projector", "quantity": 1},
                            {"type": "Whiteboard", "quantity": 2}
                        ]
                    }
                ]
            }
    """

    claims = get_jwt()
    role = claims["role"]

    authorized_Roles = ["admin", "facility_manager", "user", "auditor"]

    if role not in authorized_Roles:
        return jsonify({"error": "User not authorized to view rooms."})
    
    # Extract filters from request
    capacity = request.args.get("capacity")
    location = request.args.get("location")
    equipment = request.args.get("equipment")
    status = request.args.get("status")

    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # all rooms
        filt_request = """
            SELECT r.room_id, r.name, r.capacity, r.location, r.status
            FROM rooms r """
        # list to keep track of filters
        filters = []
        # bool value to keep track of WHERE and AND 
        bool_filter = False

        # equipment filter 
        if equipment:
            filters.append(equipment.strip())
            filt_request = filt_request + """
            JOIN room_equipment re ON re.room_id = r.room_id 
            JOIN equipment e ON e.equi_id = re.equi_id
            """
            filt_request += " WHERE e.type = ?"
            bool_filter = True
        
        # capacity filter
        if capacity:
            filt_request += " AND r.capacity >=?" if bool_filter else " WHERE r.capacity >=?" 
            filters.append(int(capacity))
            bool_filter = True

        # location filter 
        if location:
            filt_request += " AND r.location LIKE?" if bool_filter else  " WHERE r.location LIKE ?"
            filters.append(f"%{location}%")
            bool_filter = True
        
        # status filter 
        if status:
            filt_request += " AND r.status =?" if bool_filter else  " WHERE r.status = ?"
            filters.append(status.strip())
            bool_filter = True
        
        # Execute full query to return the rooms
        cur.execute(filt_request, filters)
        matched_rooms = cur.fetchall()

        # Fetch the equipment list of each matched room
        final_rooms_list = []
        for room in matched_rooms:
            cur.execute(
                """
                SELECT e.type, re.quantity
                FROM equipment e
                JOIN room_equipment re ON re.equi_id = e.equi_id
                WHERE re.room_id = ?
                """,
                (room["room_id"],)
            )
            equipment_list_rows = cur.fetchall()
            equipment_list = []
            for row in equipment_list_rows:
                equipment_list.append({
                    "type":row["type"], "quantity":row["quantity"]
                })
            final_rooms_list.append({

            "room_id": room["room_id"],
            "name": room["name"],
            "capacity": room["capacity"],
            "location": room["location"],
            "status": room["status"],
            "equipment": equipment_list
            })
    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        conn.close()

    return jsonify({"rooms": final_rooms_list}), 200

def create_app():
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = "secret_key"   
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1) # The token expires in one hour
    jwt = JWTManager(app)
    app.register_blueprint(rooms_bp)
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5002, debug=True)
