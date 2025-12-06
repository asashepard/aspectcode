// Should trigger: errors.swallowed_exception
public class SwallowedException {
    public void process() {
        try {
            riskyOperation();
        } catch (Exception e) {
            // Swallowed! No logging or handling
        }
    }
    
    private void riskyOperation() throws Exception {}
}
