# make sure the DB tables exist
# Create Flask test clients for the services

import pytest

from database.create_db import create_db_tables
from services.users_service.app import create_app as create_users_app
from services.rooms_service.app import create_app as create_rooms_app
from flask_jwt_extended import create_access_token


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """
    Ensure all tables exist before any tests run.

    """
    create_db_tables()


### Users service fixture
@pytest.fixture
def users_app():
    app = create_users_app()
    app.config["TESTING"] = True
    return app

@pytest.fixture
def users_client(users_app):
    with users_app.test_client() as client:
        yield client


### Rooms service fixture
@pytest.fixture
def rooms_app():
    app = create_rooms_app()
    app.config["TESTING"] = True
    return app

@pytest.fixture
def rooms_client(rooms_app):
    with rooms_app.test_client() as client:
        yield client


### Helper: create JWT token for a given role 
def make_token(rooms_app):
    def _make_token(role="admin", user_id=1, username="admin"):
        from flask_jwt_extended import create_access_token
        with rooms_app.app_context():
            return create_access_token(
                identity=str(user_id),
                additional_claims={"username": username, "role": role},
            )
    return _make_token
