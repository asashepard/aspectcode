// Should trigger: arch.global_state_usage
public class GlobalState {
    public static int Counter = 0;
    
    public void DoSomething() {
        // Access global state via Environment singleton - triggers arch.global_state_usage
        string user = Environment.UserName;
        string machine = Environment.MachineName;
    }
}
