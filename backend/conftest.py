# This adds the backend/ folder to Python's path
# so pytest can find the 'app' module when tests say 'from app.main import app'
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))