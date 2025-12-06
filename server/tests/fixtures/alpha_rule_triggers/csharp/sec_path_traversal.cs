// Should trigger: sec.path_traversal
using System.IO;

public class PathTraversal {
    public string ReadUserFile(string filename) {
        string path = "/app/files/" + filename;
        return File.ReadAllText(path);  // Sink!
    }
}
