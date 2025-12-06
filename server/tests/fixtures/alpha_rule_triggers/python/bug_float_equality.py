# Should trigger: bug.float_equality
def check_value(x):
    if x == 0.1 + 0.2:  # dangerous float equality
        return True
    return False
