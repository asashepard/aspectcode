# Should trigger: deadcode.unused_variable
def example():
    used = 1
    unused = 2  # unused variable
    return used
