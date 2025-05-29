import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent.parent.parent)
sys.path.append(project_root)

from backend.agents.input.speech_input import speech_to_text

test = speech_to_text()
print(test)
