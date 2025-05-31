from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict
import uuid
import datetime

app = FastAPI(
    title="Admin Dashboard API",
    description="API for managing support tickets in the admin dashboard.",
    version="0.1.0",
    openapi_tags=[
        {"name": "tickets", "description": "Operations related to support tickets."},
        {"name": "frontend", "description": "Serves the frontend application."},
    ]
)

# In-memory database for tickets
tickets_db: List[Dict] = [] # Stores TicketData as dicts

class TicketData(BaseModel):
    id: str
    user_query: str
    conversation_history: List[str]
    timestamp: str
    status: str

    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_query": "My order hasn't arrived yet.",
                "conversation_history": ["User: Where is my order?", "Agent: We are looking into it."],
                "timestamp": "2024-05-31T12:00:00.000Z",
                "status": "open"
            }
        }

class TicketCreate(BaseModel): # For receiving data, ID is not expected
    user_query: str
    conversation_history: List[str]
    timestamp: str | None = None

    class Config:
        schema_extra = {
            "example": {
                "user_query": "Cannot log into my account.",
                "conversation_history": ["User: I'm having trouble logging in.", "Agent: Have you tried resetting your password?"],
                "timestamp": "2024-06-01T10:30:00.000Z"
            }
        }

class TicketStatusUpdate(BaseModel):
    status: str

    class Config:
        schema_extra = {
            "example": {
                "status": "closed"
            }
        }

# Mount static files (for HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="admin_dashboard/static"), name="static")

# Templates for serving index.html
templates = Jinja2Templates(directory="admin_dashboard/static")

@app.get("/", tags=["frontend"], summary="Serve admin dashboard frontend", include_in_schema=False)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/tickets", response_model=TicketData, status_code=201, tags=["tickets"], summary="Create a new support ticket")
async def create_ticket(ticket_data: TicketCreate):
    """
    Create a new support ticket.
    - A unique `id` will be generated for the ticket.
    - `timestamp` will be set to the current time if not provided.
    - `status` will be initialized to "open".
    """
    new_id = str(uuid.uuid4())
    timestamp = ticket_data.timestamp or datetime.datetime.now().isoformat()

    # Convert TicketData to a dictionary before storing, or ensure tickets_db stores Pydantic models if preferred
    # For now, storing as dict to match current tickets_db type hint List[Dict]
    ticket_dict: Dict[str, Any] = { # Explicitly define as Dict
        "id": new_id,
        "user_query": ticket_data.user_query,
        "conversation_history": ticket_data.conversation_history,
        "timestamp": timestamp,
        "status": "open" # Always open on creation
    }
    tickets_db.append(ticket_dict)
    # Return the created ticket data, which will be validated by TicketData model
    return ticket_dict

@app.get("/api/tickets", response_model=List[TicketData], tags=["tickets"], summary="Retrieve all support tickets")
async def get_tickets():
    """
    Get a list of all support tickets currently in the system.
    The list can be empty if no tickets have been created.
    """
    return tickets_db

@app.put("/api/tickets/{ticket_id}/status", response_model=TicketData, tags=["tickets"], summary="Update a ticket's status")
async def update_ticket_status(ticket_id: str, status_update: TicketStatusUpdate):
    """
    Update the status of an existing ticket.
    - `ticket_id`: The UUID of the ticket to update.
    - The `timestamp` of the ticket will be updated to the current time.
    """
    for ticket_dict in tickets_db: # Assuming tickets_db stores dicts
        if ticket_dict["id"] == ticket_id:
            ticket_dict["status"] = status_update.status
            ticket_dict["timestamp"] = datetime.datetime.now().isoformat() # Update timestamp on status change
            return ticket_dict
    raise HTTPException(status_code=404, detail=f"Ticket with id {ticket_id} not found")

if __name__ == "__main__":
    import uvicorn
    # Note: The instructions mentioned port 8001 for this admin dashboard.
    # Uvicorn default is 8000. This will run on 8000 unless specified otherwise when running.
    # To run on port 8001: uvicorn admin_dashboard.main:app --reload --port 8001
    uvicorn.run(app, host="0.0.0.0", port=8001)
