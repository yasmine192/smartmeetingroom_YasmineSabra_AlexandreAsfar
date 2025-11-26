from flask import Flask, jsonify, request
import sqlite3
import os
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, get_jwt
from datetime import timedelta
from datetime import datetime 

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
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    jwt = JWTManager(app)

    #role check (matching rooms)

    def require_roles(allowed_roles):
        claims = get_jwt()
        return claims.get("role") in allowed_roles


    #health check
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"service": "bookings", "status": "ok"}), 200
    
     
    #    1) GET ALL BOOKINGS (admin + facility_manager + auditor)
    
    @app.route("/bookings", methods=["GET"])
    @jwt_required()
    def get_all_bookings():

        if not require_roles(["admin", "facility_manager", "auditor"]):
            return jsonify({"error": "Unauthorized"}), 403

        conn = get_db_connection()
        rows = conn.execute("SELECT * FROM bookings").fetchall()
        conn.close()

        return jsonify([dict(r) for r in rows]), 200



    ###############################################################
    #    HELPER: CHECK FOR TIME OVERLAP
    ###############################################################
    def booking_overlaps(cursor, room_id, new_start, new_end, exclude_booking_id=None):

        query = """
            SELECT * FROM bookings
            WHERE room_id = ?
            AND status = 'confirmed'
            AND NOT (
                end_time <= ? OR start_time >= ?
            )
        """
        params = [room_id, new_start, new_end]

        if exclude_booking_id:
            query += " AND booking_id != ?"
            params.append(exclude_booking_id)

        row = cursor.execute(query, params).fetchone()
        return row is not None



    
    #    2) CREATE BOOKING  (user creates pending booking)
    
    @app.route("/bookings", methods=["POST"])
    @jwt_required()
    def create_booking():

        identity = get_jwt_identity()
        user_role = get_jwt().get("role")
        user_id = identity

        data = request.get_json() or {}

        required = ["room_id", "start_time", "end_time"]
        missing = [f for f in required if f not in data]

        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

        room_id = data["room_id"]
        start_time = data["start_time"]
        end_time = data["end_time"]

        # Validate datetime format
        try:
            new_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
            new_end   = datetime.strptime(end_time,   "%Y-%m-%d %H:%M")
        except:
            return jsonify({"error": "Invalid datetime format. Use YYYY-MM-DD HH:MM"}), 400

        if new_end <= new_start:
            return jsonify({"error": "end_time must be after start_time"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check room exists & is available
        room = cursor.execute(
            "SELECT * FROM rooms WHERE room_id=?", (room_id,)
        ).fetchone()

        if room is None:
            return jsonify({"error": "Room not found"}), 404

        if room["status"] == "out_of_service":
            return jsonify({"error": "Room is out of service"}), 400

        # Check no overlap with *confirmed* bookings
        if booking_overlaps(cursor, room_id, start_time, end_time):
            return jsonify({"error": "Time conflict with another confirmed booking"}), 409

        # Insert booking as pending
        try:
            cursor.execute("""
                INSERT INTO bookings (start_time, end_time, status, user_id, room_id)
                VALUES (?, ?, 'pending', ?, ?)
            """, (start_time, end_time, user_id, room_id))

            conn.commit()
            booking_id = cursor.lastrowid

            return jsonify({
                "message": "Booking created (pending approval)",
                "booking_id": booking_id
            }), 201

        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()



    
    #    3) UPDATE BOOKING (only owner OR admin)
    ###############################################################
    @app.route("/bookings/<int:booking_id>", methods=["PUT"])
    @jwt_required()
    def update_booking(booking_id):

        identity = get_jwt_identity()
        role = get_jwt().get("role")
        current_user_id = identity

        data = request.get_json() or {}

        conn = get_db_connection()
        cursor = conn.cursor()

        booking = cursor.execute(
            "SELECT * FROM bookings WHERE booking_id=?", (booking_id,)
        ).fetchone()

        if booking is None:
            return jsonify({"error": "Booking not found"}), 404

        # User can edit only own booking unless admin
        if role != "admin" and booking["user_id"] != current_user_id:
            return jsonify({"error": "Unauthorized"}), 403

        # Must be pending to update
        if booking["status"] != "pending":
            return jsonify({"error": "Only pending bookings can be modified"}), 400

        new_start = data.get("start_time", booking["start_time"])
        new_end   = data.get("end_time", booking["end_time"])
        new_room  = data.get("room_id", booking["room_id"])

        try:
            ds = datetime.strptime(new_start, "%Y-%m-%d %H:%M")
            de = datetime.strptime(new_end, "%Y-%m-%d %H:%M")
        except:
            return jsonify({"error": "Invalid datetime format"}), 400

        if de <= ds:
            return jsonify({"error": "end_time must be after start_time"}), 400

        # Check overlaps
        if booking_overlaps(cursor, new_room, new_start, new_end, exclude_booking_id=booking_id):
            return jsonify({"error": "Time conflict"}), 409

        # Update now
        try:
            cursor.execute("""
                UPDATE bookings
                SET start_time=?, end_time=?, room_id=?
                WHERE booking_id=?
            """, (new_start, new_end, new_room, booking_id))

            conn.commit()
            return jsonify({"message": "Booking updated"}), 200

        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()



    
    #    4) CANCEL BOOKING  (owner OR admin)
    ###############################################################
    @app.route("/bookings/<int:booking_id>", methods=["DELETE"])
    @jwt_required()
    def cancel_booking(booking_id):

        identity = get_jwt_identity()
        role = get_jwt().get("role")
        current_user_id = identity

        conn = get_db_connection()
        cursor = conn.cursor()

        booking = cursor.execute(
            "SELECT * FROM bookings WHERE booking_id=?", (booking_id,)
        ).fetchone()

        if booking is None:
            return jsonify({"error": "Booking not found"}), 404

        if role != "admin" and booking["user_id"] != current_user_id:
            return jsonify({"error": "Unauthorized"}), 403

        try:
            cursor.execute("""
                UPDATE bookings
                SET status='cancelled'
                WHERE booking_id=?
            """, (booking_id,))

            conn.commit()
            return jsonify({"message": "Booking cancelled"}), 200

        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500

        finally:
            conn.close()



    
    #    5) ADMIN CONFIRM BOOKING
    ###############################################################
    @app.route("/bookings/<int:booking_id>/confirm", methods=["PUT"])
    @jwt_required()
    def confirm_booking(booking_id):

        if not require_roles(["admin"]):
            return jsonify({"error": "Unauthorized"}), 403

        conn = get_db_connection()
        cursor = conn.cursor()

        booking = cursor.execute(
            "SELECT * FROM bookings WHERE booking_id=?", (booking_id,)
        ).fetchone()

        if booking is None:
            return jsonify({"error": "Booking not found"}), 404

        # Confirm only pending
        if booking["status"] != "pending":
            return jsonify({"error": "Only pending bookings can be confirmed"}), 400

        # Double-check time conflict before confirming
        if booking_overlaps(cursor, booking["room_id"], booking["start_time"], booking["end_time"], exclude_booking_id=booking_id):
            return jsonify({"error": "Booking conflicts with existing confirmed booking"}), 409

        try:
            cursor.execute("""
                UPDATE bookings
                SET status='confirmed'
                WHERE booking_id=?
            """, (booking_id,))

            conn.commit()
            return jsonify({"message": "Booking confirmed"}), 200

        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()


        
    #    6) GET MY BOOKING HISTORY (logged-in user)
    ###############################################################
    @app.route("/bookings/my_history", methods=["GET"])
    @jwt_required()
    def my_booking_history():

        identity = get_jwt_identity()
        user_id = identity

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            rows = cursor.execute(
                "SELECT * FROM bookings WHERE user_id=? ORDER BY start_time DESC",
                (user_id,)
            ).fetchall()

            return jsonify({"history": [dict(r) for r in rows]}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

        
    #    7) GET BOOKING HISTORY FOR A SPECIFIC USER (admin, fm, auditor)
    ###############################################################
    @app.route("/bookings/user/<int:uid>", methods=["GET"])
    @jwt_required()
    def get_user_history(uid):

        # allowed roles
        if not require_roles(["admin", "facility_manager", "auditor"]):
            return jsonify({"error": "Unauthorized"}), 403

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # verify user exists
            user = cursor.execute(
                "SELECT user_id FROM users WHERE user_id=?", (uid,)
            ).fetchone()

            if user is None:
                return jsonify({"error": "User not found"}), 404

            rows = cursor.execute(
                "SELECT * FROM bookings WHERE user_id=? ORDER BY start_time DESC",
                (uid,)
            ).fetchall()

            return jsonify({"history": [dict(r) for r in rows]}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

        
    #    8) CHECK ROOM AVAILABILITY  (GET with query params)
    ###############################################################
    @app.route("/bookings/check_availability", methods=["GET"])
    @jwt_required()
    def check_room_availability():

        room_id = request.args.get("room_id")
        start = request.args.get("start_time")
        end   = request.args.get("end_time")

        if not room_id or not start or not end:
            return jsonify({"error": "room_id, start_time and end_time are required"}), 400

        # validate datetime format
        try:
            new_start = datetime.strptime(start, "%Y-%m-%d %H:%M")
            new_end   = datetime.strptime(end,   "%Y-%m-%d %H:%M")
        except:
            return jsonify({"error": "Invalid datetime format. Use YYYY-MM-DD HH:MM"}), 400

        if new_end <= new_start:
            return jsonify({"error": "end_time must be after start_time"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # check room exists
        room = cursor.execute(
            "SELECT * FROM rooms WHERE room_id=?", (room_id,)
        ).fetchone()

        if room is None:
            return jsonify({"error": "Room not found"}), 404

        if room["status"] == "out_of_service":
            return jsonify({"available": False, "reason": "Room out of service"}), 200

        # check overlap with confirmed bookings
        conflict = cursor.execute(
            """
            SELECT * FROM bookings
            WHERE room_id=?
            AND status='confirmed'
            AND NOT (end_time <= ? OR start_time >= ?)
            """,
            (room_id, start, end)
        ).fetchone()

        conn.close()

        if conflict:
            return jsonify({"available": False, "reason": "Time conflict"}), 200

        return jsonify({"available": True}), 200



    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5003, debug=True)
