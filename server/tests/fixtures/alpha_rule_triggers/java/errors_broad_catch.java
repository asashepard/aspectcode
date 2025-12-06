// Should trigger: errors.broad_catch
public class BroadCatch {
    public void process() {
        try {
            riskyOperation();
        } catch (Exception e) {  // Too broad!
            log(e);
        }
    }
    
    private void riskyOperation() throws Exception {}
    private void log(Exception e) {}
}
