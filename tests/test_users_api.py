import pytest 
import sqlite3

# Initialize roles
def init_roles(users_client):
    users_client.post("/roles/init")
### Delete admins helper
def clear_admins():
    conn = sqlite3.connect("./database/project.db")
    conn.execute("""
        DELETE FROM users
        WHERE role_id = (SELECT role_id FROM roles WHERE role = 'admin')
    """)
    conn.commit()
    conn.close()
### Delete all users except admin helper
def clear_users():
    conn = sqlite3.connect("./database/project.db")
    conn.execute("""
        DELETE FROM users
        WHERE role_id != (SELECT role_id FROM roles WHERE role = 'admin')
    """)
    conn.commit()
    conn.close()
 
def get_token(users_client, username, password):
    """Login and return JWT token."""
    resp = users_client.post("/users/login", json={
        "username": username,
        "password": password
    })
    return resp.get_json().get("token")


### Health test

def test_users_health(users_client):
    response = users_client.get("/health")
    # Verify the response status code
    assert response.status_code == 200
    # Verfiy the response body
    json_data = response.get_json()
    assert json_data["service"] == "users"
    assert json_data["status"] == "ok"
    assert json_data["db"] == "connected"

### Role init test

def test_roles_init(users_client):
    response = users_client.post("/roles/init")
    # Verify the response status code 
    assert response.status_code == 201
    # Verify the response body
    json_data = response.get_json()
    assert json_data["message"] == "Roles initialized (or already existed)."

###Admin init tests

    # Success Response

def test_admin_init(users_client):
    #Ensure roles exist
    users_client.post("/roles/init")

    #Delete admin if exists
    clear_admins()

    # Add a dummy admin object 
    admin_ex = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }

    response = users_client.post("/admin/init", json=admin_ex)

    assert response.status_code == 201
    json_data = response.get_json()

    assert json_data["message"] == "Admin user created successfully"
    assert json_data["admin"]["username"] == "admin"
    assert json_data["admin"]["email"] == "admin@users.com"
    assert json_data["admin"]["name"] == "Super Admin"

    # Admin Already exists error
def test_admin_init_already_exists(users_client):

    #Ensure roles exist
    users_client.post("/roles/init")

    # Post the first admin 
    admin_1 = {
        "username": "admin1",
        "email": "admin1@users.com",
        "password": "admin1",
        "name": "Super Admin 1"
    }
    users_client.post("/admin/init", json = admin_1)

    # Post second admin    
    admin_2 = {
        "username": "admin2",
        "email": "admin2@users.com",
        "password": "admin2",
        "name": "Super Admin 2"
    }
    response = users_client.post("/admin/init", json=admin_2)

    assert response.status_code == 403
    json_data = response.get_json()
    assert json_data["error"] == "Admin already initialized"

### Register a new user test

    # Success response
def test_register_user(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")

    clear_users()

    user_1 = {
            "username": "ayasabra",
            "email": "ayasabra@users.com",
            "password": "aya123",
            "name": "Aya Sabra"
        }
    response = users_client.post("/users/register", json = user_1)
    assert response.status_code  == 201
    json_data = response.get_json()
    assert json_data["message"] == "User registered successfully"
    assert json_data["user"]["username"] == "ayasabra"
    assert json_data["user"]["email"] == "ayasabra@users.com"
    assert json_data["user"]["name"] == "Aya Sabra"
    assert json_data["user"]["role"] == "user"

def test_register_user_already_exists(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")

    # Give user 2 a username and email that already exist
    user_2 = {
            "username": "ayasabra",
            "email": "ayasabra@users.com",
            "password": "aya0988",
            "name": "Amani Sabra"
        }
    response = users_client.post("/users/register", json = user_2)
    assert response.status_code  == 409
    json_data = response.get_json()
    assert json_data["error"] == "Username or email already exists"


### Test login API

    # Success test

def test_login_existing_user(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users
    clear_users()

    # register a user
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)

    # Login info
    user_1_login ={
        "username": "ayasabra",
        "password": "aya123",
    }
    # login
    response = users_client.post("/users/login", json = user_1_login)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["message"] == "Login successful"
    assert "token" in json_data 
    assert json_data["user"]["username"] == "ayasabra"
    assert json_data["user"]["email"] == "ayasabra@users.com"
    assert json_data["user"]["role"] == "user"

    # Invalid username or password 

def test_login_invalid_credentials(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users
    clear_users()

    # register a user
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)

    # Login info
    user_1_wrong_username ={
        "username": "wrong_username", # incorrect
        "password": "aya123", #correct
    }
    user_1_wrong_password ={
        "username": "ayasabra", # correct
        "password": "wrong_password", #incorrect
    }
    # login
    response1 = users_client.post("/users/login", json = user_1_wrong_username)
    response2 = users_client.post("/users/login", json = user_1_wrong_password)

    # test wrong username
    assert response1.status_code == 401
    json_data1 = response1.get_json()
    assert json_data1["error"] == "Invalid username or password"
    
    # test wrong password
    assert response2.status_code == 401
    json_data2 = response2.get_json()
    assert json_data2["error"] == "Invalid username or password"

    # Missing username or password
def test_login_missing_credentials(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users
    clear_users()

    # register a user
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)

    # Login info
    user_1_missing_username ={
        "password": "aya123", 
    }
    user_1_missing_password ={
        "username": "ayasabra", 
    }
    # login
    response1 = users_client.post("/users/login", json = user_1_missing_username)
    response2 = users_client.post("/users/login", json = user_1_missing_password)

    # test wrong username
    assert response1.status_code == 400
    json_data1 = response1.get_json()
    assert json_data1["error"] == "Username and password are required to login."
    
    # test wrong password
    assert response2.status_code == 400
    json_data2 = response2.get_json()
    assert json_data2["error"] == "Username and password are required to login."


### Test Read Own Profile API 

    # Success response

def test_get_my_profile(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users 
    clear_users()
    # register a user
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)
    # Get TOKEN
    token = get_token(users_client, "ayasabra", "aya123")
    # read profile
    response = users_client.get("/users/me", headers = {"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["username"] == "ayasabra"
    assert json_data["email"] == "ayasabra@users.com"
    assert json_data["name"] == "Aya Sabra"
    assert json_data["role"] == "user"

### Test Update own profile API 

    # Success 
def test_update_own_profile(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users 
    clear_users()
    # register a user
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)
    # Get TOKEN
    token = get_token(users_client, "ayasabra", "aya123")

    new_data = {
        "username": "updated_aya_sabra",
        "email": "updated_ayasabra@users.com",
        "password": "updated_aya123",
        "name": "Updated Aya Sabra"      
    }
    
    response = users_client.put("/users/me", json = new_data, headers = {"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["message"] == "Profile updated successfully"
    assert json_data["user"]["username"] == "updated_aya_sabra"
    assert json_data["user"]["email"] == "updated_ayasabra@users.com"
    assert json_data["user"]["name"] == "Updated Aya Sabra"

    # Username or email already exist
def test_update_own_profile_username_email_conflict(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users 
    clear_users()
    # register a user
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    user_2 = {
        "username": "yasminesabra",
        "email": "yasminesabra@users.com",
        "password": "yasmine123",
        "name": "Yasmine Sabra"
    }
    users_client.post("/users/register", json = user_1)
    users_client.post("/users/register", json = user_2)

    # Get TOKEN
    token = get_token(users_client, "ayasabra", "aya123")

    new_data_duplicate_username = {
        "username": "yasminesabra"  # already exists
    }
    new_data_duplicate_email= {
        "email": "yasminesabra@users.com"  # already exists
    }
    response1 = users_client.put("/users/me", json = new_data_duplicate_username, headers = {"Authorization": f"Bearer {token}"})
    assert response1.status_code == 409
    json_data1 = response1.get_json()
    assert json_data1["error"] == "Username or email already exists"

    response2 = users_client.put("/users/me", json = new_data_duplicate_email, headers = {"Authorization": f"Bearer {token}"})
    assert response2.status_code == 409
    json_data2 = response2.get_json()
    assert json_data2["error"] == "Username or email already exists"

    # not fields provided
def test_update_own_profile_no_fields_provided(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users 
    clear_users()
    # register a user
    user = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user)
    token = get_token(users_client, "ayasabra", "aya123")

    new_data = {}   # no fields provided

    response = users_client.put("/users/me", json = new_data, headers = {"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["error"] == "No fields to update"

### Test delete own account API 

    # Success response
def test_delete_own_profile(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users 
    clear_users()
    # register a user
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)
    # Get TOKEN
    token = get_token(users_client, "ayasabra", "aya123")

    response = users_client.delete("/users/delete", json = {"password": "aya123"}, headers = {"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    json_data = response.get_json()
    assert "Account deleted successfully" in json_data["message"] 

        # Missing password - incorrect password
def test_delete_own_profile_missing_icorrect_password(users_client):
    # Ensure roles exist
    users_client.post("/roles/init")
    # Clear users 
    clear_users()
    # register a user
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)
    # Get TOKEN
    token = get_token(users_client, "ayasabra", "aya123")
    
    response = users_client.delete("/users/delete", json = {}, headers = {"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["error"] == "Password confirmation is required"

    response1 = users_client.delete("/users/delete", json = {"password": "incorrect"}, headers = {"Authorization": f"Bearer {token}"})
    assert response1.status_code == 401
    json_data1 = response1.get_json()
    assert json_data1["error"] == "Incorrect password"


### Test the assign - change user role (only admin API)

# Success test
def test_admin_assign_role(users_client):
    #Ensure roles exist
    users_client.post("/roles/init")

    #Delete admin if exists
    clear_admins()

    # Add a dummy admin object 
    admin = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }

    users_client.post("/admin/init", json=admin)
    token = get_token(users_client, "admin", "admin123")

    # register a user 
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)
    # Fetch user_id of u1
    conn = sqlite3.connect("./database/project.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username='ayasabra'")
    user_id = cur.fetchone()[0]
    conn.close()

    # role change
    response = users_client.put(f"/users/{user_id}/role", json = {"role" : "facility_manager"}, headers = {"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["message"] == "Role updated successfully"
    assert json_data["user"]["user_id"] == user_id
    assert json_data["user"]["new_role"] == "facility_manager"

# Non admin request 
def test_assign_forbidden_role(users_client):
    #Ensure roles exist
    users_client.post("/roles/init")

    #Delete admin if exists
    clear_admins()
    clear_users()

    # register a user 
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)
    token = get_token(users_client, "ayasabra", "aya123")

    # role change
    response = users_client.put(f"/users/1/role", json = {"role" : "facility_manager"}, headers = {"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    json_data = response.get_json()
    assert json_data["error"] == "Only admins are authorized to modify users' related information."

# Assigning non existent role
def test_assign_invalid_role(users_client):
    #Ensure roles exist
    users_client.post("/roles/init")

    #Delete admin if exists
    clear_admins()

    # Add a dummy admin object 
    admin = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }

    users_client.post("/admin/init", json=admin)
    token = get_token(users_client, "admin", "admin123")

    # register a user 
    user_1 = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = user_1)
    # Fetch user_id of u1
    conn = sqlite3.connect("./database/project.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username='ayasabra'")
    user_id = cur.fetchone()[0]
    conn.close()

    # role change
    response = users_client.put(f"/users/{user_id}/role", json = {"role" : "Assistant"}, headers = {"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["error"] == "Invalid role"

### Test get all users API (admins and auditors)
# Success 
def test_get_all_users(users_client):
    #Ensure roles exist
    users_client.post("/roles/init")

    #Delete admin if exists
    clear_admins()

    # Add a dummy admin object 
    admin = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }

    users_client.post("/admin/init", json=admin)
    admin_token = get_token(users_client, "admin", "admin123")

    # register a user 
    auditor = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = auditor)
    conn = sqlite3.connect("./database/project.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username='ayasabra'")
    user_id = cur.fetchone()[0]
    conn.close()

    # role change
    users_client.put(f"/users/{user_id}/role", json = {"role" : "auditor"}, headers = {"Authorization": f"Bearer {admin_token}"})
    auditor_token = get_token(users_client, "ayasabra", "aya123")

    # Creating users 
    users_client.post("/users/register", json={
        "username": "u1",
        "email": "u1@demo.com",
        "password": "1234",
        "name": "User One"
    })


    users_client.post("/users/register", json={
        "username": "u2",
        "email": "u2@demo.com",
        "password": "5678",
        "name": "User Two"
    })

    response_admin = users_client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert response_admin.status_code == 200
    json_data_admin = response_admin.get_json()
    assert "users" in json_data_admin
    assert len(json_data_admin["users"]) == 4

    response_auditor = users_client.get("/users", headers={"Authorization": f"Bearer {auditor_token}"})
    assert response_auditor.status_code == 200
    json_data_auditor = response_auditor.get_json()
    assert "users" in json_data_auditor
    assert len(json_data_auditor["users"]) == 4

# Unauthorized user 
def test_get_all_users_forbidden(users_client):
    users_client.post("/roles/init")
    clear_admins()
    clear_users()

    users_client.post("/users/register", json={
        "username": "yasminesabra",
        "email": "yasminesabra@users.com",
        "password": "yasmine1234",
        "name": "Yasmine Sabra"
    })

    token = get_token(users_client, "yasminesabra", "yasmine1234")

    response = users_client.get(
        "/users",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "Not authorized."

### Test get user by username 
# Success 
def test_get_user(users_client):
    #Ensure roles exist
    users_client.post("/roles/init")

    #Delete admin if exists
    clear_admins()

    # Add a dummy admin object 
    admin = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }

    users_client.post("/admin/init", json=admin)
    admin_token = get_token(users_client, "admin", "admin123")

    # register a user 
    auditor = {
        "username": "ayasabra",
        "email": "ayasabra@users.com",
        "password": "aya123",
        "name": "Aya Sabra"
    }
    users_client.post("/users/register", json = auditor)
    conn = sqlite3.connect("./database/project.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username='ayasabra'")
    user_id = cur.fetchone()[0]
    conn.close()

    # role change
    users_client.put(f"/users/{user_id}/role", json = {"role" : "auditor"}, headers = {"Authorization": f"Bearer {admin_token}"})
    auditor_token = get_token(users_client, "ayasabra", "aya123")

    # Creating a user
    users_client.post("/users/register", json={
        "username": "test_username",
        "email": "tes@users.com",
        "password": "test1234",
        "name": "Test User"
    })

    response_admin = users_client.get("/username/test_username", headers={"Authorization": f"Bearer {admin_token}"})
    assert response_admin.status_code == 200
    json_data_admin = response_admin.get_json()
    assert json_data_admin["username"] == "test_username"
    assert json_data_admin["email"] == "tes@users.com"
    assert json_data_admin["name"] == "Test User"

    response_auditor = users_client.get("/username/test_username", headers={"Authorization": f"Bearer {auditor_token}"})
    assert response_auditor.status_code == 200
    json_data_auditor = response_auditor.get_json()
    assert json_data_auditor["username"] == "test_username"
    assert json_data_auditor["email"] == "tes@users.com"
    assert json_data_auditor["name"] == "Test User"

# Unauthorized user 
def test_get_user_forbidden(users_client):
    users_client.post("/roles/init")
    clear_admins()
    clear_users()

    users_client.post("/users/register", json={
        "username": "yasminesabra",
        "email": "yasminesabra@users.com",
        "password": "yasmine1234",
        "name": "Yasmine Sabra"
    })

    # test user
    users_client.post("/users/register", json={
        "username": "test_username",
        "email": "tes@users.com",
        "password": "test1234",
        "name": "Test User"
    })

    token = get_token(users_client, "yasminesabra", "yasmine1234")

    response = users_client.get(
        "/username/test_username",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "Not authorized."

### Resetting password 
def test_reset_password(users_client):
    users_client.post("/roles/init")
    clear_admins()
    clear_users()

    # Create admin
    admin = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }
    users_client.post("/admin/init", json=admin)
    admin_token = get_token(users_client, "admin", "admin123")

    # test user
    users_client.post("/users/register", json={
        "username": "test_username",
        "email": "tes@users.com",
        "password": "test1234",
        "name": "Test User"
    })

    conn = sqlite3.connect("./database/project.db")
    user_id = conn.execute("SELECT user_id FROM users WHERE username='test_username'").fetchone()[0]
    conn.close()

    response = users_client.put(
        f"/users/{user_id}/reset-password",
        json={"password": "admin123"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.get_json()["message"] == "Password reset successfully."

# Unauthorized 
def test_reset_password_forbidden_non_admin(users_client):
    users_client.post("/roles/init")
    clear_admins()
    clear_users()

    # Create normal user
    users_client.post("/users/register", json={
        "username": "yasminesabra",
        "email": "yasminesabra@users.com",
        "password": "yasmine1234",
        "name": "Yasmine Sabra"
    })
    token = get_token(users_client, "yasminesabra", "yasmine1234")

    response = users_client.put(
        "/users/1/reset-password",
        json={"password": "reset_password"},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "Only admins can reset passwords."

# Missing password field 
def test_reset_password_missing_password(users_client):
    users_client.post("/roles/init")
    clear_admins()
    clear_users()

    admin = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }
    users_client.post("/admin/init", json=admin)
    admin_token = get_token(users_client, "admin", "admin123")

    response = users_client.put(
        "/users/1/reset-password",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "New password is required."

### Test delete user by admin API 
#success
def test_delete_user(users_client):
    users_client.post("/roles/init")
    clear_admins()
    clear_users()

    # Create admin
    admin = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }
    users_client.post("/admin/init", json=admin)
    admin_token = get_token(users_client, "admin", "admin123")

    # test user
    users_client.post("/users/register", json={
        "username": "test_username",
        "email": "tes@users.com",
        "password": "test1234",
        "name": "Test User"
    })

    conn = sqlite3.connect("./database/project.db")
    user_id = conn.execute("SELECT user_id FROM users WHERE username='test_username'").fetchone()[0]
    conn.close()

    response = users_client.delete(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.get_json()["message"] == "User deleted successfully."
    assert response.get_json()["user_id_deleted"] == user_id

# Unauthorized user 
def test_delete_user_forbidden_non_admin(users_client):
    users_client.post("/roles/init")
    clear_admins()
    clear_users()

    # Create normal user
    users_client.post("/users/register", json={
        "username": "yasminesabra",
        "email": "yasminesabra@users.com",
        "password": "yasmine1234",
        "name": "Yasmine Sabra"
    })
    token = get_token(users_client, "yasminesabra", "yasmine1234")

    response = users_client.delete(
        "/users/1",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "Only admins can delete users."

# Admin cannot delete themselves 
def test_delete_admin(users_client):
    users_client.post("/roles/init")
    clear_admins()
    clear_users()

    # Create admin
    admin = {
        "username": "admin",
        "email": "admin@users.com",
        "password": "admin123",
        "name": "Super Admin"
    }
    users_client.post("/admin/init", json=admin)
    admin_token = get_token(users_client, "admin", "admin123")

    conn = sqlite3.connect("./database/project.db")
    user_id = conn.execute("SELECT user_id FROM users WHERE username='admin'").fetchone()[0]
    conn.close()

    response = users_client.delete(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Admins cannot delete their own account."
