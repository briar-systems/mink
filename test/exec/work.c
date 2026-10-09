/* the second object of the static executable lane: data, zero fill and read
   only data reached from another object, and a function nothing calls */

static const long table[4] = {3, 5, 7, 11};
long total = 10;
long scratch[8];

long unused(long x) {
    return x * 3;
}

long work(long seed) {
    for (int i = 0; i < 4; i++) {
        scratch[i] = table[i] + seed;
    }
    for (int i = 0; i < 4; i++) {
        total += scratch[i] - seed;
    }
    return total + seed - 1;
}
