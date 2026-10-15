/* data, zero fill and read-only data reached across objects, a table of
   function pointers, and a string literal both objects hold, which the
   linker may merge */

#include "rt.h"

extern long counts[4];
extern const long weights[4];
extern long (*const steps[3])(long);
long fold(long seed);

static long scratch[16];

int program(void) {
    long sum = fold(3);
    for (int i = 0; i < 16; i++) {
        scratch[i] = i * weights[i % 4];
        sum += scratch[i];
    }
    for (int i = 0; i < 3; i++) {
        sum = steps[i](sum);
        counts[i] += 1;
    }
    rt_text("shared literal\n");
    rt_text("sum ");
    rt_number(sum);
    rt_text("\n");
    return (int)(sum % 200) + counts[0] + counts[1] + counts[2];
}
