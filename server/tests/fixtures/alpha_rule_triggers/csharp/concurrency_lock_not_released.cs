// Should trigger: concurrency.lock_not_released
using System.Threading;

public class LockNotReleased {
    private readonly object _lock = new object();
    
    public void Process(bool condition) {
        Monitor.Enter(_lock);  // Not in try-finally!
        if (condition) {
            return;  // Early return without Exit!
        }
        DoWork();
        Monitor.Exit(_lock);
    }
    
    private void DoWork() {}
}
