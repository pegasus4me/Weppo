from langchain_ollama import ChatOllama
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from typing import List, Dict, Any
from ..mcp.shopify_server import ShopifyMCPServer
from .prompt_template import promptTemplate
from .product_search import ShopifySearchTool
from langchain_xai import ChatXAI
import os
from dotenv import load_dotenv


from backend.agents.input.speech_input import speech_to_text

load_dotenv()
google_api_key: str = os.environ.get('GOOGLE_API_KEY')
deepseek_api_key: str = "sk-4070045196d1492c8f5c98aea8526326"
xai_api_key: str = os.environ.get('XAI_API_KEY')

class PersonalShopperAgent:
    """
    A personal shopping assistant that helps customers find products and provides guidance.
    """
    
    def __init__(self, store_domain: str):
        # Initialize MCP server
        self.mcp_server = ShopifyMCPServer(store_domain)
        
        # Initialize XAI with proper configuration
        self.llm = ChatXAI(
            model="grok-3-mini",
            temperature=0.3,  # Lower temperature for more consistent responses
            api_key=xai_api_key,
            max_tokens=1500,  # Increased token limit significantly
            # Remove format="json" as it's not needed for conversational responses
        )
        
        # Initialize memory
        self.memory = MemorySaver()
        
        # Initialize tools with proper BaseTool implementation
        self.tools = [
            ShopifySearchTool(self.mcp_server)
        ]
        
        # Initialize prompt template
        self.prompt = promptTemplate()
        
        # Initialize agent executor
        self.agent_executor = create_react_agent(
            model=self.llm,
            tools=self.tools,
            checkpointer=self.memory,
            debug=False,  # Turn off debug to reduce noise
            prompt=self.prompt
        )
    
    def chat(self, user_query: str, thread_id: str = "default") -> str:
        """
        Process a user query and return a helpful response with product suggestions
        """
        try:
            # Configure thread for memory
            config = {"configurable": {"thread_id": thread_id}}
            
            # Stream the agent's response
            messages = []
            for step in self.agent_executor.stream(
                {"messages": [HumanMessage(content=user_query)]},
                config,
                stream_mode="values",
            ):
                if step["messages"]:
                    messages = step["messages"]
            
            # Extract and clean the final response
            if messages:
                last_message = messages[-1]
                return self._extract_clean_response(last_message)
            else:
                return "I'm sorry, I couldn't process your request. Please try again."
                
        except Exception as e:
            return f"I encountered an error: {str(e)}. Please try rephrasing your question."
    
    def _extract_clean_response(self, message) -> str:
        """
        Extract clean response from the agent message, handling various message types
        """
        try:
            # Handle AIMessage objects
            if isinstance(message, AIMessage):
                content = message.content
                
                # If content is empty, try to extract from additional_kwargs
                if not content and 'reasoning_content' in message.additional_kwargs:
                    # This means the model hit token limits during reasoning
                    return 'token limits '
                
                # Clean up any remaining artifacts from the raw response
                if isinstance(content, str):
                    # Remove debug information and format properly
                    cleaned_content = self._clean_response_content(content)
                    return cleaned_content
                
                return str(content) if content else "I'm sorry, I couldn't generate a proper response."
            
            # Handle other message types
            elif hasattr(message, 'content'):
                return str(message.content)
            else:
                return str(message)
                
        except Exception as e:
            print(f"Error extracting response: {e}")
            return "I apologize, but I encountered an issue formatting my response. Please try asking again."
    
    def _clean_response_content(self, content: str) -> str:
        """
        Clean and format the response content
        """
        # Remove any debug markers or raw data
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Skip debug lines, empty lines, and system messages
            if (line.startswith('[') or 
                line.startswith('messages ->') or 
                line.startswith('checkpoint') or
                'State at the end' in line or
                not line.strip()):
                continue
            cleaned_lines.append(line.strip())
        
        return '\n'.join(cleaned_lines).strip()
    
    
    def get_recommendations(self, user_query: str) -> List[Dict[str, Any]]:
        """
        Get product recommendations based on user query
        """
        try:
            results = self.mcp_server.get_products(user_query)
            return results.get('result', {}).get('products', [])
        except Exception as e:
            print(f"Error getting recommendations: {e}")
            return []


if __name__ == "__main__":
    print("Welcome to the Personal Shopping Assistant!")
    print("Type 'exit' or 'quit' to end the conversation.")
    print("Type 'voice' to use voice input.")
    print("-" * 50)
    
    agent = PersonalShopperAgent("www.allbirds.com")
    
    while True:
        try:
            # Get input method choice
            input_method = input("\nChoose input method (text/voice) [default: text]: ").strip().lower()
            
            # Get user input based on chosen method
            if input_method == 'voice':
                print("\n🎤 Listening... (Speak now, will auto-send after 4 seconds of silence)")
                user_input = speech_to_text()
                if user_input:
                    print(f"\nYou said: {user_input}")
                    # Get response from agent
                    print("\nAssistant: ")
                    response = agent.chat(user_input, thread_id="1234")
                    print(response)
                else:
                    print("\nNo speech detected. Please try again.")
            else:
                user_input = input("\nYou: ").strip()
                
                # Check for exit command
                if user_input.lower() in ['exit', 'quit']:
                    print("\nThank you for chatting! Goodbye!")
                    break
                
                # Skip empty inputs
                if not user_input:
                    continue
                    
                # Get response from agent
                print("\nAssistant: ")
                response = agent.chat(user_input, thread_id="1234")
                print(response)
            
        except KeyboardInterrupt:
            print("\n\nThank you for chatting! Goodbye!")
            break
        except Exception as e:
            print(f"\nAn error occurred: {str(e)}")
            print("Please try again or type 'exit' to quit.")