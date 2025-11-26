import sqlite3

DB_NAME = "project.db"

def connect_to_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def create_db_tables():
    conn = connect_to_db()
    try:
        conn.executescript(
            """
            -- ROLES
            CREATE TABLE IF NOT EXISTS roles (
                role_id     INTEGER PRIMARY KEY,
                role        TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL
            );

            -- USERS
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT NOT NULL UNIQUE,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                name          TEXT NOT NULL,
                role_id       INTEGER NOT NULL,
                FOREIGN KEY (role_id) REFERENCES roles(role_id)
            );

            -- ROOMS
            CREATE TABLE IF NOT EXISTS rooms (
                room_id  INTEGER PRIMARY KEY,
                name     TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                location TEXT NOT NULL,
                status   TEXT NOT NULL CHECK (
                                status IN ('available','booked','out_of_service')
                         )
            );

            -- EQUIPMENT
            CREATE TABLE IF NOT EXISTS equipment (
                equi_id INTEGER PRIMARY KEY,
                type    TEXT NOT NULL
            );

            -- ROOMS ↔ EQUIPMENT
            CREATE TABLE IF NOT EXISTS room_equipment (
                room_id  INTEGER NOT NULL,
                equi_id  INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (room_id, equi_id),
                FOREIGN KEY (room_id) REFERENCES rooms(room_id),
                FOREIGN KEY (equi_id) REFERENCES equipment(equi_id)
            );

            -- BOOKINGS
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY,
                start_time TEXT NOT NULL,
                end_time   TEXT NOT NULL,
                status     TEXT NOT NULL CHECK (
                                status IN ('confirmed','cancelled', 'pending')
                          ),
                user_id    INTEGER NOT NULL,
                room_id    INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE
            );

            -- REVIEWS
            CREATE TABLE IF NOT EXISTS reviews (
                review_id   INTEGER PRIMARY KEY,
                rating      INTEGER NOT NULL,
                comment     TEXT,
                flag_status TEXT NOT NULL CHECK (
                                flag_status IN ('clean','flagged')
                             ),
                user_id     INTEGER NOT NULL,
                room_id     INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (room_id) REFERENCES rooms(room_id)
            );
            """
        )
        conn.commit()
        print("All tables created successfully!")
    except sqlite3.Error as e:
        print("Table creation failed:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    create_db_tables()
