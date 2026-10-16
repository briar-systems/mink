/* the C program of the WASI lane, on wasi-libc: it prints a line and exits
   42 only when its constructors ran lowest priority first */
int puts(const char *);
static int order[2];
static int n;
__attribute__((constructor(200))) static void late(void) { order[n++] = 2; }
__attribute__((constructor(101))) static void early(void) { order[n++] = 1; }
int main(void) { puts("hello from mink"); return order[0] == 1 && order[1] == 2 ? 42 : 1; }
