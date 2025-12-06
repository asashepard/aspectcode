# Should trigger: arch.external_integration
# HTTP client call - external service
import requests

def fetch_user_data(user_id):
    """External HTTP integration - REST API call"""
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()

# Database connection
import sqlite3

def get_database_connection():
    """External database integration"""
    conn = sqlite3.connect("app.db")
    return conn
