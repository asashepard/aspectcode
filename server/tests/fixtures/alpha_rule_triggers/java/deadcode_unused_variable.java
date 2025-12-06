// Should trigger: deadcode.unused_variable
public class UnusedVar {
    public void process() {
        int unusedValue = 42;  // Never used!
        String result = "ok";
        System.out.println(result);
    }
}
