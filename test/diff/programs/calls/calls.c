/* recursion, a dense switch the compiler may lower to a jump table, a static
   function, and a function nothing calls, which a link that collects
   sections drops */

#include "rt.h"

static long fib(long n) {
    return n < 2 ? n : fib(n - 1) + fib(n - 2);
}

long unreached(long x) {
    return x * 31;
}

long pick(int k, long v) {
    switch (k) {
    case 0: return v + 1;
    case 1: return v * 3;
    case 2: return v - 7;
    case 3: return v ^ 0x55;
    case 4: return v << 2;
    case 5: return v >> 1;
    case 6: return -v;
    default: return v;
    }
}

int program(void) {
    long v = fib(15);
    for (int k = 0; k < 8; k++) {
        v = pick(k, v);
    }
    rt_text("calls ");
    rt_number(v);
    rt_text("\n");
    return (int)(v & 0x7f);
}
