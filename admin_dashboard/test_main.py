import pytest
from fastapi.testclient import TestClient
from admin_dashboard.main import app, tickets_db, TicketData # Adjust import if your app structure is different

# Fixture to clear the tickets_db before each test
@pytest.fixture(autouse=True)
def clear_db_before_each_test():
    tickets_db.clear()

client = TestClient(app)

def test_create_ticket():
    """Test creating a new ticket."""
    ticket_payload = {
        "user_query": "My package is delayed.",
        "conversation_history": ["User: Where is it?", "Agent: Checking..."]
    }
    response = client.post("/api/tickets", json=ticket_payload)
    assert response.status_code == 201 # Checks for successful creation
    data = response.json()
    assert data["user_query"] == ticket_payload["user_query"]
    assert data["conversation_history"] == ticket_payload["conversation_history"]
    assert data["status"] == "open"
    assert "id" in data
    assert "timestamp" in data

    # Verify it's in our "DB"
    assert len(tickets_db) == 1
    assert tickets_db[0]["id"] == data["id"]

def test_get_tickets_empty():
    """Test getting tickets when none exist."""
    response = client.get("/api/tickets")
    assert response.status_code == 200
    assert response.json() == []

def test_get_tickets_with_data():
    """Test getting tickets when some exist."""
    # Create a couple of tickets directly in the db for testing GET
    ticket1_data = {
        "user_query": "Query 1",
        "conversation_history": ["Test1"],
        "id": "test-id-1",
        "timestamp": "2023-01-01T00:00:00Z",
        "status": "open"
    }
    ticket2_data = {
        "user_query": "Query 2",
        "conversation_history": ["Test2"],
        "id": "test-id-2",
        "timestamp": "2023-01-02T00:00:00Z",
        "status": "closed"
    }
    tickets_db.append(ticket1_data)
    tickets_db.append(ticket2_data)

    response = client.get("/api/tickets")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Order isn't guaranteed, so check for presence
    response_ids = {ticket["id"] for ticket in data}
    assert "test-id-1" in response_ids
    assert "test-id-2" in response_ids

def test_update_ticket_status_found():
    """Test updating the status of an existing ticket."""
    # Create a ticket
    ticket_payload = {
        "user_query": "Status update test",
        "conversation_history": []
    }
    create_response = client.post("/api/tickets", json=ticket_payload)
    assert create_response.status_code == 201
    ticket_id = create_response.json()["id"]

    # Update its status
    update_payload = {"status": "closed"}
    update_response = client.put(f"/api/tickets/{ticket_id}/status", json=update_payload)
    assert update_response.status_code == 200
    updated_data = update_response.json()
    assert updated_data["status"] == "closed"
    assert updated_data["id"] == ticket_id

    # Verify in DB
    found_ticket = next((t for t in tickets_db if t["id"] == ticket_id), None)
    assert found_ticket is not None
    assert found_ticket["status"] == "closed"
    original_timestamp = create_response.json()["timestamp"]
    assert updated_data["timestamp"] != original_timestamp # Timestamp should update

def test_update_ticket_status_not_found():
    """Test updating the status of a non-existent ticket."""
    update_payload = {"status": "closed"}
    response = client.put("/api/tickets/non-existent-id/status", json=update_payload)
    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket with id non-existent-id not found"}

def test_ticket_data_model_id_field():
    """Ensure TicketData model includes 'id' for response validation."""
    # This test is more about ensuring the Pydantic model used for response_model
    # in GET /api/tickets and PUT /api/tickets/{ticket_id}/status includes 'id'.
    # If TicketData model is missing 'id', GET requests would likely fail validation.

    # Create a ticket
    ticket_payload = {
        "user_query": "ID field test",
        "conversation_history": []
    }
    create_response = client.post("/api/tickets", json=ticket_payload)
    assert create_response.status_code == 201
    created_ticket_id = create_response.json()["id"]

    # Fetch all tickets and check structure of the first one
    get_response = client.get("/api/tickets")
    assert get_response.status_code == 200
    tickets = get_response.json()
    assert len(tickets) > 0
    assert "id" in tickets[0]
    assert tickets[0]["id"] == created_ticket_id

    # Update status and check structure
    update_payload = {"status": "pending"}
    update_response = client.put(f"/api/tickets/{created_ticket_id}/status", json=update_payload)
    assert update_response.status_code == 200
    assert "id" in update_response.json()
    assert update_response.json()["id"] == created_ticket_id

# To run these tests, navigate to the repository root and run:
# python -m pytest admin_dashboard
# (Ensure admin_dashboard is discoverable by Python, e.g. by setting PYTHONPATH or running from correct dir)
# Or, if admin_dashboard/main.py can be run as a module:
# pytest admin_dashboard/test_main.py
# (Ensure __init__.py might be needed in admin_dashboard for older pytest/python versions if using the first method)

# For these tests to pass directly with `pytest admin_dashboard/test_main.py`,
# ensure that the import `from admin_dashboard.main import app, tickets_db` works.
# This usually means your project root (containing admin_dashboard) should be in PYTHONPATH.
# If running pytest from the root, it often handles this automatically.
# Example: If repo root is /path/to/Weppo/, and tests are in /path/to/Weppo/admin_dashboard/test_main.py
# Running `pytest` from /path/to/Weppo/ should work.
# Or `python -m pytest` from /path/to/Weppo/
