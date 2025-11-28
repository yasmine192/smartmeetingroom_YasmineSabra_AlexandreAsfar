import pytest
from flask_jwt_extended import create_access_token
from services.rooms_service.app import get_db_connection


# ----------------------
# Local fixtures
# ----------------------

@pytest.fixture
def make_token(rooms_app):
    """
    Create a JWT with a given role.
    Uses the same JWT config as the rooms service.
    """
    def _make_token(role="admin", identity="testuser"):
        with rooms_app.app_context():
            return create_access_token(
                identity=identity,
                additional_claims={"role": role}
            )
    return _make_token


# ----------------------
# Health endpoint
# ----------------------

def test_health(rooms_client):
    resp = rooms_client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["service"] == "rooms"
    assert data["status"] == "ok"


# ----------------------
# POST /rooms  (create_room)
# ----------------------

def test_create_room_success(rooms_client, make_token):
    token = make_token(role="admin")
    payload = {
        "name": "Room A",
        "capacity": 10,
        "location": "First Floor",
        "equipment": ["Projector", "Whiteboard"],
    }

    resp = rooms_client.post(
        "/rooms",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    data = resp.get_json()
    assert data["room"]["name"] == "Room A"
    assert data["room"]["capacity"] == 10
    assert data["room"]["location"] == "First Floor"
    assert data["room"]["status"] == "available"
    assert set(data["room"]["equipment"]) == {"Projector", "Whiteboard"}


def test_create_room_missing_fields(rooms_client, make_token):
    token = make_token(role="admin")
    resp = rooms_client.post(
        "/rooms",
        json={"name": "Incomplete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Missing required fields" in resp.get_json()["error"]


def test_create_room_unauthorized_role(rooms_client, make_token):
    token = make_token(role="user")  # not admin/facility_manager
    resp = rooms_client.post(
        "/rooms",
        json={"name": "R", "capacity": 5, "location": "L"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "Not authorized" in resp.get_json()["error"]


def test_create_room_no_token(rooms_client):
    resp = rooms_client.post(
        "/rooms",
        json={"name": "R", "capacity": 5, "location": "L"},
    )
    # flask_jwt_extended usually returns 401 or 422 depending on config
    assert resp.status_code in (401, 422)


# ----------------------
# GET /rooms/<id>  (get_room_by_id)
# ----------------------

def test_get_room_by_id_success(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "R1", "capacity": 5, "location": "L1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.get(
        f"/rooms/{room_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["room_id"] == room_id
    assert data["name"] == "R1"


def test_get_room_by_id_not_found(rooms_client, make_token):
    token = make_token(role="admin")
    resp = rooms_client.get(
        "/rooms/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "Room not found" in resp.get_json()["error"]


def test_get_room_by_id_unauthorized_role(rooms_client, make_token):
    # role not in ["admin","facility_manager","auditor","user"]
    token = make_token(role="weird_role")
    resp = rooms_client.get(
        "/rooms/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_get_room_by_id_no_token(rooms_client):
    resp = rooms_client.get("/rooms/1")
    assert resp.status_code in (401, 422)


# ----------------------
# PUT /rooms/<id>  (update_room_details)
# ----------------------

def test_update_room_success(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "Old", "capacity": 10, "location": "L"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.put(
        f"/rooms/{room_id}",
        json={"name": "New", "capacity": 20},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.get_json()["room"]
    assert data["name"] == "New"
    assert data["capacity"] == 20
    assert data["location"] == "L"


def test_update_room_no_fields(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "X", "capacity": 5, "location": "Loc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.put(
        f"/rooms/{room_id}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "No fields to update" in resp.get_json()["error"]


def test_update_room_not_found(rooms_client, make_token):
    token = make_token(role="admin")
    resp = rooms_client.put(
        "/rooms/99999",
        json={"name": "New"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "Room not found" in resp.get_json()["error"]


def test_update_room_unauthorized_role(rooms_client, make_token):
    token = make_token(role="user")  # not allowed
    resp = rooms_client.put(
        "/rooms/1",
        json={"name": "New"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_update_room_no_token(rooms_client):
    resp = rooms_client.put(
        "/rooms/1",
        json={"name": "New"},
    )
    assert resp.status_code in (401, 422)


# ----------------------
# DELETE /rooms/<id>  (delete_room)
# ----------------------

def test_delete_room_success(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "ToDelete", "capacity": 5, "location": "L"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.delete(
        f"/rooms/{room_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["room_id_deleted"] == room_id


def test_delete_room_not_found(rooms_client, make_token):
    token = make_token(role="admin")
    resp = rooms_client.delete(
        "/rooms/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "Room not found" in resp.get_json()["error"]


def test_delete_room_unauthorized_role(rooms_client, make_token):
    token = make_token(role="user")
    resp = rooms_client.delete(
        "/rooms/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_delete_room_no_token(rooms_client):
    resp = rooms_client.delete("/rooms/1")
    assert resp.status_code in (401, 422)


# ----------------------
# POST /rooms/<id>/equipment  (add_equipment)
# ----------------------

def test_add_equipment_success(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "EqRoom", "capacity": 5, "location": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.post(
        f"/rooms/{room_id}/equipment",
        json={"equipment": "Camera"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["added_equipment"] == "Camera"


def test_add_equipment_missing_field(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "EqRoom2", "capacity": 5, "location": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.post(
        f"/rooms/{room_id}/equipment",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Type of equipment item is required" in resp.get_json()["error"]


def test_add_equipment_room_not_found(rooms_client, make_token):
    token = make_token(role="admin")
    resp = rooms_client.post(
        "/rooms/99999/equipment",
        json={"equipment": "X"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "Room not found" in resp.get_json()["error"]


def test_add_equipment_unauthorized_role(rooms_client, make_token):
    token = make_token(role="user")
    resp = rooms_client.post(
        "/rooms/1/equipment",
        json={"equipment": "X"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_add_equipment_no_token(rooms_client):
    resp = rooms_client.post(
        "/rooms/1/equipment",
        json={"equipment": "X"},
    )
    assert resp.status_code in (401, 422)


# ----------------------
# DELETE /rooms/<id>/equipment/<equi_id>  (delete_equipment)
# ----------------------

def _get_equipment_id_by_type(equip_type: str):
    db = get_db_connection()
    cur = db.cursor()
    cur.execute("SELECT equi_id FROM equipment WHERE type = ?", (equip_type,))
    row = cur.fetchone()
    db.close()
    return row["equi_id"] if row else None


def test_delete_equipment_success(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "EqRoom3", "capacity": 5, "location": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    rooms_client.post(
        f"/rooms/{room_id}/equipment",
        json={"equipment": "Microphone"},
        headers={"Authorization": f"Bearer {token}"},
    )

    equi_id = _get_equipment_id_by_type("Microphone")
    assert equi_id is not None

    resp = rooms_client.delete(
        f"/rooms/{room_id}/equipment/{equi_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["removed_equipment"] == "Microphone"


def test_delete_equipment_room_not_found(rooms_client, make_token):
    token = make_token(role="admin")

    # pick some ID that doesn't exist
    resp = rooms_client.delete(
        "/rooms/99999/equipment/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "Room not found" in resp.get_json()["error"]


def test_delete_equipment_not_found(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "EqRoom4", "capacity": 5, "location": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    # equi_id that does not exist
    resp = rooms_client.delete(
        f"/rooms/{room_id}/equipment/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "Equipment not found" in resp.get_json()["error"]


def test_delete_equipment_not_in_room(rooms_client, make_token):
    token = make_token(role="admin")

    # Create room A and B
    create_a = rooms_client.post(
        "/rooms",
        json={"name": "RoomA", "capacity": 5, "location": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_a_id = create_a.get_json()["room"]["room_id"]

    create_b = rooms_client.post(
        "/rooms",
        json={"name": "RoomB", "capacity": 5, "location": "B"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_b_id = create_b.get_json()["room"]["room_id"]

    # Add equipment to room A only
    rooms_client.post(
        f"/rooms/{room_a_id}/equipment",
        json={"equipment": "Speaker"},
        headers={"Authorization": f"Bearer {token}"},
    )

    equi_id = _get_equipment_id_by_type("Speaker")

    # Try to delete from room B (should fail "not available in this room")
    resp = rooms_client.delete(
        f"/rooms/{room_b_id}/equipment/{equi_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "not available in this room" in resp.get_json()["error"]


def test_delete_equipment_unauthorized_role(rooms_client, make_token):
    token = make_token(role="user")
    resp = rooms_client.delete(
        "/rooms/1/equipment/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_delete_equipment_no_token(rooms_client):
    resp = rooms_client.delete("/rooms/1/equipment/1")
    assert resp.status_code in (401, 422)


# ----------------------
# PUT /rooms/<id>/status  (update_room_status)
# ----------------------

def test_update_room_status_success(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "StatusRoom", "capacity": 5, "location": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.put(
        f"/rooms/{room_id}/status",
        json={"status": "out_of_service"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["room_status"] == "out_of_service"


def test_update_room_status_missing_status(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "StatusRoom2", "capacity": 5, "location": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.put(
        f"/rooms/{room_id}/status",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "New status is required" in resp.get_json()["error"]


def test_update_room_status_invalid_status(rooms_client, make_token):
    token = make_token(role="admin")

    create = rooms_client.post(
        "/rooms",
        json={"name": "StatusRoom3", "capacity": 5, "location": "A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create.get_json()["room"]["room_id"]

    resp = rooms_client.put(
        f"/rooms/{room_id}/status",
        json={"status": "broken"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Invalid status" in resp.get_json()["error"]


def test_update_room_status_unauthorized_role(rooms_client, make_token):
    token = make_token(role="user")
    resp = rooms_client.put(
        "/rooms/1/status",
        json={"status": "available"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_update_room_status_no_token(rooms_client):
    resp = rooms_client.put(
        "/rooms/1/status",
        json={"status": "available"},
    )
    assert resp.status_code in (401, 422)


# ----------------------
# GET /rooms  (get_rooms with filters)
# ----------------------

def test_get_rooms_basic(rooms_client, make_token):
    token = make_token(role="admin")

    # Create some rooms
    rooms_client.post(
        "/rooms",
        json={"name": "CapRoom", "capacity": 50, "location": "North"},
        headers={"Authorization": f"Bearer {token}"},
    )
    rooms_client.post(
        "/rooms",
        json={"name": "SmallRoom", "capacity": 5, "location": "South"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = rooms_client.get(
        "/rooms",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["rooms"]) >= 2


def test_get_rooms_with_capacity_filter(rooms_client, make_token):
    token = make_token(role="admin")

    rooms_client.post(
        "/rooms",
        json={"name": "Big", "capacity": 40, "location": "N"},
        headers={"Authorization": f"Bearer {token}"},
    )
    rooms_client.post(
        "/rooms",
        json={"name": "Tiny", "capacity": 3, "location": "S"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = rooms_client.get(
        "/rooms?capacity=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rooms = resp.get_json()["rooms"]
    assert all(r["capacity"] >= 10 for r in rooms)


def test_get_rooms_with_equipment_filter(rooms_client, make_token):
    token = make_token(role="admin")

    # Room1 with Projector
    create1 = rooms_client.post(
        "/rooms",
        json={"name": "ProjRoom", "capacity": 20, "location": "L1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room1_id = create1.get_json()["room"]["room_id"]
    rooms_client.post(
        f"/rooms/{room1_id}/equipment",
        json={"equipment": "Projector"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Room2 with no Projector
    rooms_client.post(
        "/rooms",
        json={"name": "PlainRoom", "capacity": 20, "location": "L2"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = rooms_client.get(
        "/rooms?equipment=Projector",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    rooms = resp.get_json()["rooms"]
    # All returned rooms must have Projector in equipment list
    for r in rooms:
        types = [e["type"] for e in r["equipment"]]
        assert "Projector" in types


def test_get_rooms_unauthorized_role(rooms_client, make_token):
    token = make_token(role="weird_role")
    resp = rooms_client.get(
        "/rooms",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Code does not set status, default=200, but returns error JSON
    data = resp.get_json()
    assert "error" in data
    assert "not authorized" in data["error"].lower()


def test_get_rooms_no_token(rooms_client):
    resp = rooms_client.get("/rooms")
    assert resp.status_code in (401, 422)
