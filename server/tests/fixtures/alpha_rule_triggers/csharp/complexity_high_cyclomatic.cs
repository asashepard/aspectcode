// Should trigger: complexity.high_cyclomatic
public class HighComplexity {
    public string Classify(int a, int b, int c, int d, int e) {
        if (a > 0) {
            if (b > 0) {
                if (c > 0) {
                    if (d > 0) {
                        if (e > 0) {
                            return "all positive";
                        } else if (e < 0) {
                            return "e negative";
                        }
                    } else if (d < 0) {
                        return "d negative";
                    }
                } else if (c < 0) {
                    return "c negative";
                }
            } else if (b < 0) {
                return "b negative";
            }
        } else if (a < 0) {
            return "a negative";
        }
        return "default";
    }
}
