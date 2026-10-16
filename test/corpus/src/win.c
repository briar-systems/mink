/* a freestanding windows image: an entry point, an export, a call into a dll
   the link loads on first use, thread local data and a load configuration
   that asks for control flow guard and states code integrity fields, so
   lld-link fills the guard tables. the load configuration is written in
   assembly, as its guard flags are a link-time constant C cannot take */
extern int dep_value(int);
_Thread_local int tls_count = 3;

__declspec(dllexport) int exported(int x)
{
    return dep_value(x) + tls_count;
}

int (*volatile indirect)(int) = exported;

int entry(void)
{
    return indirect(7);
}

/* what the CRT would supply: the delay load helper the link calls through,
   the guard check routines and the thread-local directory's bounds */
#ifdef _M_IX86
#define CC __stdcall
__asm__(".globl __tls_array\n.set __tls_array, 44\n");
#else
#define CC
#endif
void *CC __delayLoadHelper2(const void *descriptor, void **slot)
{
    return *slot;
}
static void check_icall(void) {}
void (*__guard_check_icall_fptr)(void) = check_icall;
void (*__guard_dispatch_icall_fptr)(void) = check_icall;
unsigned long _tls_index;
__attribute__((section(".tls"))) char _tls_start = 0;
__attribute__((section(".tls$ZZZ"))) char _tls_end = 0;
#ifdef _WIN64
unsigned long long __security_cookie = 0x2b992ddfa232;
#else
unsigned int __security_cookie = 0xbb40e64e;
#endif

/* the ARM64EC helpers the CRT would supply, and its metadata, which the link
   builds and the load configuration points at */
#ifdef _M_ARM64EC
void __icall_helper_arm64ec(void) {}
#define CHPE "__chpe_metadata"
#else
#define CHPE "0"
#endif

#ifdef _M_IX86
#define S(x) "_" #x
#else
#define S(x) #x
#endif
#ifdef _WIN64
#define W ".quad "
#define SIZE "320"
#else
#define W ".long "
#define SIZE "192"
#endif

__asm__(
    ".section .rdata,\"dr\"\n"
    ".globl " S(_load_config_used) "\n"
    ".p2align 3\n"
    S(_load_config_used) ":\n"
    ".long " SIZE ", 0\n"
    ".short 0, 0\n"
    ".long 0, 0, 0\n"
    W "0, 0, 0, 0, 0, 0\n"
    ".long 0\n"
    ".short 0, 0\n"
    W "0, " S(__security_cookie) ", 0, 0\n"
    W S(__guard_check_icall_fptr) ", " S(__guard_dispatch_icall_fptr) ", " S(__guard_fids_table) ", " S(__guard_fids_count) "\n"
    ".long " S(__guard_flags) "\n"
    ".short 1, 0xffff\n"
    ".long 0x10, 0\n"
    W S(__guard_iat_table) ", " S(__guard_iat_count) ", " S(__guard_longjmp_table) ", " S(__guard_longjmp_count) "\n"
    W "0, " CHPE ", 0, 0\n"
    ".long 0\n"
    ".short 0, 0\n"
    W "0\n"
    ".long 0, 0\n"
    W "0, 0, " S(__guard_eh_cont_table) ", " S(__guard_eh_cont_count) "\n"
    W S(__guard_check_icall_fptr) ", " S(__guard_dispatch_icall_fptr) ", " S(__guard_dispatch_icall_fptr) ", " S(__security_cookie) ", " S(__guard_check_icall_fptr) "\n"
    ".text\n");
