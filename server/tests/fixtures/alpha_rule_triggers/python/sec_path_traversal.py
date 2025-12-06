# Should trigger: sec.path_traversal
def read_user_file(filename):
    path = "/app/files/" + filename
    with open(path, 'r') as f:
        return f.read()
