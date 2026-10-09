/* the start file of the static executable lane: _start, write and exit over
   the linux system call of each architecture, with no C library */

long work(long seed);

static long call3(long n, long a, long b, long c) {
#if defined(__x86_64__)
    register long r __asm__("rax") = n;
    __asm__ volatile("syscall" : "+r"(r) : "D"(a), "S"(b), "d"(c) : "rcx", "r11", "memory");
    return r;
#elif defined(__aarch64__)
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2) : "memory");
    return x0;
#elif defined(__riscv)
    register long a7 __asm__("a7") = n;
    register long a0 __asm__("a0") = a;
    register long a1 __asm__("a1") = b;
    register long a2 __asm__("a2") = c;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a7), "r"(a1), "r"(a2) : "memory");
    return a0;
#else
#error "no system call for this architecture"
#endif
}

#if defined(__x86_64__)
enum { SYS_WRITE = 1, SYS_EXIT = 60 };
#else
enum { SYS_WRITE = 64, SYS_EXIT = 93 };
#endif

static const char greeting[] = "hello from mink\n";

void _start(void) {
    call3(SYS_WRITE, 1, (long)greeting, sizeof greeting - 1);
    call3(SYS_EXIT, work(7), 0, 0);
    for (;;) {
    }
}
