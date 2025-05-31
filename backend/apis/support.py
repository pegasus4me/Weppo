from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Set
import datetime
import uuid
import json
import logging # Added

router = APIRouter()
logger = logging.getLogger(__name__) # Added

# In-memory storage for tickets
db_tickets: Dict[str, 'Ticket'] = {}

class TicketInput(BaseModel):
    user_id: str = Field(..., example="user123")
    issue_description: str = Field(..., example="Cannot connect to the payment gateway.")
    priority: Optional[str] = Field("medium", example="high")
    status: Optional[str] = Field("open", example="open")

class Ticket(TicketInput):
    ticket_id: str = Field(default_factory=lambda: str(uuid.uuid4()), example="a1b2c3d4-e5f6-7890-1234-567890abcdef")
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    updated_at: Optional[datetime.datetime] = None

class TicketUpdateInput(BaseModel):
    issue_description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

# Connection Manager for WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # self.scoped_connections: Dict[str, Set[WebSocket]] = {} # For advanced ticket-scoped connections

    async def connect(self, websocket: WebSocket, ticket_id: Optional[str] = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket connection: {websocket.client} for ticket '{ticket_id}'. Total global connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, ticket_id: Optional[str] = None):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected: {websocket.client} from ticket '{ticket_id}'. Total global connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_to_ticket(self, message: str, ticket_id: str): # ticket_id currently for logging/payload
        logger.info(f"Broadcasting message for ticket {ticket_id} to all {len(self.active_connections)} connections (basic manager).")
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@router.post("/create", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(ticket_in: TicketInput):
    logger.info(f"Received request to create ticket for user: {ticket_in.user_id} with issue: '{ticket_in.issue_description[:50]}...'")
    new_ticket = Ticket(**ticket_in.model_dump())
    db_tickets[new_ticket.ticket_id] = new_ticket
    logger.info(f"Ticket created with ID: {new_ticket.ticket_id} for user: {new_ticket.user_id}")
    return new_ticket

@router.get("/ticket/list", response_model=List[Ticket])
async def list_tickets(user_id: Optional[str] = None, status: Optional[str] = None):
    logger.info(f"Received request to list tickets. Filters: user_id={user_id}, status={status}")
    tickets_to_return = list(db_tickets.values())

    if user_id:
        tickets_to_return = [t for t in tickets_to_return if t.user_id == user_id]
    if status:
        tickets_to_return = [t for t in tickets_to_return if t.status == status]

    logger.info(f"Returning {len(tickets_to_return)} tickets based on filters.")
    return tickets_to_return

@router.put("/ticket/update/{ticket_id}", response_model=Ticket)
async def update_ticket(ticket_id: str, ticket_update: TicketUpdateInput):
    logger.info(f"Received request to update ticket ID: {ticket_id} with data: {ticket_update.model_dump(exclude_unset=True)}")
    if ticket_id not in db_tickets:
        logger.error(f"Error: Ticket ID {ticket_id} not found for update.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket with ID {ticket_id} not found")

    stored_ticket = db_tickets[ticket_id]
    update_data = ticket_update.model_dump(exclude_unset=True)

    if not update_data:
        logger.warning(f"Update request for ticket ID {ticket_id} received with no fields to update. Returning current state.")
        return stored_ticket

    for field, value in update_data.items():
        setattr(stored_ticket, field, value)

    stored_ticket.updated_at = datetime.datetime.utcnow()
    db_tickets[stored_ticket.ticket_id] = stored_ticket

    logger.info(f"Ticket ID {ticket_id} updated successfully.")
    return stored_ticket

# WebSocket endpoint for real-time ticket conversation
@router.websocket("/ticket/conversation/{ticket_id}")
async def ticket_conversation_ws(websocket: WebSocket, ticket_id: str):
    await manager.connect(websocket, ticket_id)

    if ticket_id not in db_tickets:
        logger.warning(f"Client {websocket.client} connected to WebSocket for non-existent ticket ID: {ticket_id}")
        # Consider sending an error message and closing if ticket must exist for conversation
        # error_payload = json.dumps({"error": "Ticket not found", "ticket_id": ticket_id, "message": "Cannot start conversation for a non-existent ticket."})
        # await manager.send_personal_message(error_payload, websocket)
        # await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        # manager.disconnect(websocket, ticket_id) # Ensure manager knows client is gone
        # return # Important to exit if closing early

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"WS Message received on ticket/{ticket_id} from {websocket.client}: {data[:100]}...") # Log snippet

            try:
                message_data = json.loads(data)
                text_content = message_data.get("text", "Error: Malformed message, text field missing.")
            except json.JSONDecodeError:
                logger.debug(f"Message from {websocket.client} on ticket/{ticket_id} is not valid JSON. Treating as plain text.")
                text_content = data # Raw data as text

            response_payload = {
                "ticket_id": ticket_id,
                "sender_info": f"{websocket.client.host}:{websocket.client.port}",
                "text": text_content,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }

            await manager.broadcast_to_ticket(json.dumps(response_payload), ticket_id)

    except WebSocketDisconnect:
        manager.disconnect(websocket, ticket_id)
        logger.info(f"Client {websocket.client} disconnected from ticket/{ticket_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket for ticket/{ticket_id} from {websocket.client}: {e}", exc_info=True)
        manager.disconnect(websocket, ticket_id) # Ensure disconnect
        # Consider sending a WebSocket close message with an error code if possible
        # if websocket.client_state == websockets.protocol.State.OPEN:
        #    await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        # Fallback disconnect, e.g. if error occurs before try block or not caught by specific excepts
        if websocket in manager.active_connections:
             manager.disconnect(websocket, ticket_id)
             logger.debug(f"Fallback disconnect executed for {websocket.client} on ticket/{ticket_id}")
