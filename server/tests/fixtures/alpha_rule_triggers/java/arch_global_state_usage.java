// Should trigger: arch.global_state_usage
public class GlobalState {
    public static int counter = 0;
    
    public void doSomething() {
        // Access global state via System singleton - triggers arch.global_state_usage
        String prop = System.getProperty("user.home");
        Runtime rt = Runtime.getRuntime();
    }
}
