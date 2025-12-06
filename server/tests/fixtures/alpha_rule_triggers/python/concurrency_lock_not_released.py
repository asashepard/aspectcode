# Should trigger: concurrency.lock_not_released
import threading

lock = threading.Lock()

def critical_section():
    lock.acquire()
    if condition():
        return  # Early return without releasing lock!
    do_work()
    lock.release()
    
def condition():
    return True

def do_work():
    pass
