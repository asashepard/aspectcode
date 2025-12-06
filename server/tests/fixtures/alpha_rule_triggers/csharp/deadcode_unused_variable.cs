// Should trigger: deadcode.unused_variable
public class UnusedVar {
    public void Process() {
        int unusedValue = 42;  // Never used!
        string result = "ok";
        Console.WriteLine(result);
    }
}
