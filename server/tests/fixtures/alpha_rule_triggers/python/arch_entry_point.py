# Should trigger: arch.entry_point
# Flask HTTP endpoint
from flask import Flask

app = Flask(__name__)

@app.route('/api/users')
def get_users():
    """HTTP entry point - GET /api/users"""
    return {"users": []}

# Main function entry point
def main():
    """Application main entry point"""
    print("Starting application...")
    app.run()

if __name__ == "__main__":
    main()
