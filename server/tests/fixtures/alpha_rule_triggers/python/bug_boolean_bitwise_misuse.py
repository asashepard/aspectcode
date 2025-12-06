# Should trigger: bug.boolean_bitwise_misuse
def check_conditions(a, b, c, d):
    if (a == 1) & (b > 0):  # using bitwise & instead of logical and
        return True
    if (c < 10) | (d == 5):  # using bitwise | instead of logical or
        return True
    return False
