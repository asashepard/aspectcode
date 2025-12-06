// Should trigger: ident.duplicate_definition
public class DuplicateDef {
    public void process() {
        System.out.println("first");
    }
}

class DuplicateDef {  // Duplicate class definition!
    public void process() {
        System.out.println("second");
    }
}
