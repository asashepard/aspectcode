# Should trigger: sec.insecure_random
import random

def generate_token():
    return str(random.randint(100000, 999999))
