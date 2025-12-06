// Should trigger: errors.swallowed_exception
public class SwallowedException {
    public void Process() {
        try {
            RiskyOperation();
        } catch {
            // Swallowed! No handling
        }
    }
    
    private void RiskyOperation() {}
}
