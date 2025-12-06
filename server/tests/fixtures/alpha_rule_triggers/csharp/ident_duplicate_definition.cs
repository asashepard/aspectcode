// Should trigger: ident.duplicate_definition
public class DuplicateDef {
    public void Process() {
        Console.WriteLine("first");
    }
}

class DuplicateDef {  // Duplicate class definition!
    public void Process() {
        Console.WriteLine("second");
    }
}
