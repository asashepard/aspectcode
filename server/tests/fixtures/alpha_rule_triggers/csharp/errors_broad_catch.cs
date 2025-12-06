// Should trigger: errors.broad_catch
public class BroadCatch {
    public void Process() {
        try {
            RiskyOperation();
        } catch (Exception e) {  // Too broad!
            Log(e);
        }
    }
    
    private void RiskyOperation() {}
    private void Log(Exception e) {}
}
