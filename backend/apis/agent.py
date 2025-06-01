from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.agents.orchestrator.agent import PersonalShopperAgent
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
# Corrected path to be relative to this file's location (backend/apis/) to reach backend/.env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

router = APIRouter()
STORE_DOMAIN = "www.allbirds.com"  # test
# Initial checks for API keys are removed here as they are better handled in initialize_agent
# and will prevent agent_instance from being created if missing.
agent_instance = None

class AgentRequest(BaseModel):
    user_query: str
    thread_id: str = "default"

class AgentResponse(BaseModel):
    response: str

@router.post("/process", response_model=AgentResponse)
async def process_agent_request(request_data: AgentRequest): # Renamed 'request' to 'request_data'
    logger.info(f"Agent process request received for thread_id: {request_data.thread_id} with query: '{request_data.user_query[:50]}...'")
    global agent_instance
    if not agent_instance:
        logger.error("Agent instance is not available. It should have been initialized at startup.")
        raise HTTPException(status_code=503, detail="Agent service is currently unavailable.")

    try:
        agent_response_text = agent_instance.chat(user_query=request_data.user_query, thread_id=request_data.thread_id)
        logger.info(f"Agent response generated for thread_id: {request_data.thread_id}. Response length: {len(agent_response_text)}")
        return AgentResponse(response=agent_response_text)
    except Exception as e:
        logger.error(f"Error during agent chat for thread_id {request_data.thread_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing request with agent: {str(e)}")

# Helper function to be called at startup by main.py's lifespan manager
def initialize_agent():
    global agent_instance
    logger.info(f"Attempting to initialize PersonalShopperAgent with domain: {STORE_DOMAIN}")

    required_env_vars = ["XAI_API_KEY", "GOOGLE_API_KEY", "SHOPIFY_STORE_DOMAIN"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing essential environment variables for agent initialization: {', '.join(missing_vars)}. Agent initialization aborted.")
        agent_instance = None
        return

    try:
        agent_instance = PersonalShopperAgent(store_domain=STORE_DOMAIN)
        logger.info("PersonalShopperAgent initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize PersonalShopperAgent: {e}", exc_info=True)
        agent_instance = None