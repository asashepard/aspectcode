# Should trigger: ident.shadowing
x = 10

def outer():
    x = 20  # shadows global x
    
    def inner():
        x = 30  # shadows outer x
        return x
    
    return inner()
