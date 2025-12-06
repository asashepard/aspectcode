// Should trigger: sec.insecure_random
using System;

public class InsecureRandom {
    public int GenerateToken() {
        Random random = new Random();  // Not crypto-secure!
        return random.Next();
    }
}
