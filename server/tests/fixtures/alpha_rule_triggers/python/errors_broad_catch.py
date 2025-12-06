# Should trigger: errors.broad_catch
def handle_error():
    try:
        process_data()
    except Exception as e:  # too broad
        print(f"Error: {e}")
        
def process_data():
    pass
