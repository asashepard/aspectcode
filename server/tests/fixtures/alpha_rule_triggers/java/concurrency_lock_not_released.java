// Should trigger: concurrency.lock_not_released
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantLock;

public class LockNotReleased {
    private Lock lock = new ReentrantLock();
    
    public void process(boolean condition) {
        lock.lock();  // Not in try-finally!
        if (condition) {
            return;  // Early return without unlock!
        }
        doWork();
        lock.unlock();
    }
    
    private void doWork() {}
}
