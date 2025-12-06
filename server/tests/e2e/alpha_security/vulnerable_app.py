"""
Alpha Security Test Project

This project contains intentional security vulnerabilities that should be caught 
by alpha security rules:
- sec.command_injection
- sec.eval_exec_usage  
- sec.hardcoded_secret
- sec.insecure_random
- sec.open_redirect
- sec.path_traversal
- sec.sql_injection_concat
- sec.weak_hashing
- sec.xss_unescaped_html
- security.jwt_without_exp
"""

import os
import hashlib
import random
import subprocess
import sqlite3
from flask import Flask, request, jsonify, redirect
import jwt


app = Flask(__name__)

# sec.hardcoded_secret - Hardcoded API key
API_KEY = "sk_live_1234567890abcdef"
SECRET_KEY = "super_secret_password_123"

# sec.weak_hashing - Using MD5 for password hashing
def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

# sec.insecure_random - Using random for security purposes
def generate_token():
    return str(random.randint(1000000, 9999999))

@app.route('/execute')
def execute_command():
    """sec.command_injection - Direct command execution"""
    cmd = request.args.get('cmd')
    if cmd:
        # Vulnerable: direct command injection
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout
    return "No command provided"

@app.route('/eval')
def eval_code():
    """sec.eval_exec_usage - Dynamic code execution"""
    code = request.args.get('code')
    if code:
        # Vulnerable: eval usage
        result = eval(code)
        return str(result)
    return "No code provided"

@app.route('/redirect')
def redirect_user():
    """sec.open_redirect - Unvalidated redirect"""
    url = request.args.get('url')
    if url:
        # Vulnerable: unvalidated redirect
        return redirect(url)
    return "No URL provided"

@app.route('/file')
def read_file():
    """sec.path_traversal - Directory traversal vulnerability"""
    filename = request.args.get('file')
    if filename:
        # Vulnerable: path traversal
        try:
            with open(f"/app/files/{filename}", 'r') as f:
                return f.read()
        except Exception as e:
            return f"Error: {e}"
    return "No file specified"

@app.route('/search')
def search_users():
    """sec.sql_injection_concat - SQL injection via concatenation"""
    term = request.args.get('q')
    if term:
        # Vulnerable: SQL injection through string concatenation
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        query = f"SELECT * FROM users WHERE name = '{term}'"
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        return jsonify(results)
    return "No search term provided"

@app.route('/comment')
def show_comment():
    """sec.xss_unescaped_html - XSS through unescaped HTML"""
    comment = request.args.get('comment')
    if comment:
        # Vulnerable: unescaped HTML output
        return f"<div>Comment: {comment}</div>"
    return "No comment provided"

@app.route('/login', methods=['POST'])
def login():
    """security.jwt_without_exp - JWT without expiration"""
    username = request.json.get('username')
    password = request.json.get('password')
    
    if username and password:
        # Vulnerable: JWT without expiration time
        token = jwt.encode({
            'user': username,
            'role': 'user'
            # Missing 'exp' field
        }, SECRET_KEY, algorithm='HS256')
        
        return jsonify({'token': token})
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/admin')
def admin_panel():
    """Additional function to test JWT usage"""
    token = request.headers.get('Authorization')
    if token:
        try:
            # This would also be vulnerable to tokens without expiration
            payload = jwt.decode(token.replace('Bearer ', ''), SECRET_KEY, algorithms=['HS256'])
            return f"Welcome admin: {payload['user']}"
        except Exception as e:
            return f"Token error: {e}", 401
    return "Authorization required", 401


if __name__ == '__main__':
    app.run(debug=True)