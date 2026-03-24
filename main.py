import os

# Check if we are in testing mode
if os.getenv('TESTING'):
    # Conditional imports for testing
    from crew_runner import *
    from metrics import *
    from utils.file_utils import *
    from config import *
    
# Rest of your main.py code would go here...