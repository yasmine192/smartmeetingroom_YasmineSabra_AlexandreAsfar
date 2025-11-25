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
    return conn

def create_app():
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = "secret_key"   
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1) # The token expires in one hour
    jwt = JWTManager(app)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"service": "rooms", "status": "ok"}), 200
    
    """API to create a new room"""
    @app.route("/rooms", methods=["POST"]) 
    @jwt_required()
    def create_room():
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
    

    """API to edit room details: name, capacity, location"""
    @app.route("/rooms/<int:room_id>", methods=["PUT"]) 
    @jwt_required()
    def update_room_details(room_id):
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

    """API to get room details by ID"""
    @app.route("/rooms/<int:room_id>", methods=["GET"]) 
    @jwt_required()
    def get_room_by_id(room_id):
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


    

    """API to delete a room with bookings cancellation and reviews removal"""
    @app.route("/rooms/<int:room_id>", methods=["DELETE"])
    @jwt_required()
    def delete_room(room_id):
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


    """API to add a room equipment"""
    @app.route("/rooms/<int:room_id>/equipment", methods=["POST"])
    @jwt_required()
    def add_equipment(room_id):
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
    

    """API to delete a room equipment"""
    @app.route("/rooms/<int:room_id>/equipment/<int:equi_id>", methods=["DELETE"])
    @jwt_required()
    def delete_equipment(room_id, equi_id):
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
    
    """API to mark a room out of service/available again"""
    @app.route("/rooms/<int:room_id>/status", methods =["PUT"])
    @jwt_required()
    def update_room_status(room_id):
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


    """API to get all rooms with filters"""
    @app.route("/rooms", methods =["GET"])
    @jwt_required()
    def get_rooms():
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

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5002, debug=True)