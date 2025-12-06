// Should trigger: complexity.high_cyclomatic
function complexFunction(a: boolean, b: boolean, c: boolean, d: boolean, e: boolean, f: boolean, g: boolean, h: boolean, i: boolean, j: boolean, k: boolean): number {
    if (a) return 1;
    else if (b) return 2;
    else if (c) return 3;
    else if (d) return 4;
    else if (e) return 5;
    else if (f) return 6;
    else if (g) return 7;
    else if (h) return 8;
    else if (i) return 9;
    else if (j) return 10;
    else if (k) return 11;
    else return 0;
}
