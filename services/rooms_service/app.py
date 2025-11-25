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

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5002, debug=True)
