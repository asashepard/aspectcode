// Should trigger: sec.path_traversal
import java.io.*;
import java.nio.file.*;

public class PathTraversal {
    public byte[] readUserFile(String filename) throws IOException {
        // Rule looks for: new File, Paths.get, Files.readAllBytes, etc.
        String userPath = "/app/files/" + filename;
        File file = new File(userPath);  // This is a sink!
        return Files.readAllBytes(Paths.get(userPath));  // Also a sink
    }
}
