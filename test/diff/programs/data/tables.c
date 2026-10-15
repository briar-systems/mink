/* the second object of the data program */

#include "rt.h"

long counts[4] = {1, 2, 3, 4};
const long weights[4] = {2, 3, 5, 7};

static long twice(long x) {
    return x * 2;
}

static long less(long x) {
    return x - 11;
}

static long more(long x) {
    return x + 101;
}

long (*const steps[3])(long) = {twice, less, more};

long fold(long seed) {
    rt_text("shared literal\n");
    long acc = seed;
    for (int i = 0; i < 4; i++) {
        acc = acc * 3 + counts[i];
    }
    return acc;
}
