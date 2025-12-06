# Should trigger: arch.global_state_usage
GLOBAL_COUNTER = 0

def increment():
    global GLOBAL_COUNTER
    GLOBAL_COUNTER += 1
    return GLOBAL_COUNTER
