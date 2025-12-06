// Should trigger: bug.iteration_modification
using System.Collections.Generic;

public class IterationBug {
    public void RemoveItems(List<string> items) {
        foreach (var item in items) {
            if (string.IsNullOrEmpty(item)) {
                items.Remove(item);  // InvalidOperationException!
            }
        }
    }
}
