import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent.parent.parent)
sys.path.append(project_root)

from backend.agents.input.speech_input import speech_to_text

# test = speech_to_text()
# print(test)

# TODO: This test needs to be rewritten to properly test
# the streaming speech-to-text functionality.
# Current implementation relies on MicrophoneStream by default
# or a WebSocketStream, neither of which is easily mockable here
# without significant test infrastructure.
# Manual testing with a WebSocket client is recommended for now.
