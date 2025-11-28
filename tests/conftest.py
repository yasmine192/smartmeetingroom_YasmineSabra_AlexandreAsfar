import pytest

from database.create_db import create_db_tables
from services.users_service.app import create_app as create_users_app
from services.rooms_service.app import create_app as create_rooms_app
from flask_jwt_extended import create_access_token


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """
    Ensure all tables exist before any tests run.

    NOTE: This uses your normal project.db.
    For clean testing, run tests on a fresh DB (delete project.db or
    re-run create_db.py before pytest).
    """
    create_db_tables()


# ---------- USERS SERVICE FIXTURES ----------

@pytest.fixture
def users_app():
    app = create_users_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def users_client(users_app):
    with users_app.test_client() as client:
        yield client


# ---------- ROOMS SERVICE FIXTURES ----------

@pytest.fixture
def rooms_app():
    app = create_rooms_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def rooms_client(rooms_app):
    with rooms_app.test_client() as client:
        yield client


# Helper: create JWT token for a given role (used in rooms tests)
@pytest.fixture
def make_token(rooms_app):
    def _make_token(role="admin", user_id=1, username="admin"):
        from flask_jwt_extended import create_access_token
        with rooms_app.app_context():
            return create_access_token(
                identity=str(user_id),
                additional_claims={"username": username, "role": role},
            )
    return _make_token
