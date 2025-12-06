# Should trigger: sec.open_redirect
from flask import redirect, request

def handle_redirect():
    url = request.args.get('url')
    return redirect(url)
