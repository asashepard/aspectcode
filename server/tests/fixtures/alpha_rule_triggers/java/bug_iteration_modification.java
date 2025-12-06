// Should trigger: bug.iteration_modification
import java.util.*;

public class IterationBug {
    public void removeItems(List<String> items) {
        for (String item : items) {
            if (item.isEmpty()) {
                items.remove(item);  // ConcurrentModificationException!
            }
        }
    }
}
