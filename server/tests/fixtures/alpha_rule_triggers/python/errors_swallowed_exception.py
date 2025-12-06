# Should trigger: errors.swallowed_exception
def risky_operation():
    try:
        do_something()
    except Exception:
        pass  # swallowed exception
        
def do_something():
    raise ValueError("error")
