// Should trigger: sec.insecure_random
import java.util.Random;

public class InsecureRandom {
    public String generateToken() {
        Random random = new Random();  // Insecure for crypto!
        return String.valueOf(random.nextInt());
    }
}
