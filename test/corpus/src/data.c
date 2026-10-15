/* data of every kind: bss, rodata, custom and aligned sections, constructors.
   mach-o names a section by segment and section, and has no symbol aliases */
#ifdef __APPLE__
#define CUSTOM_SECTION "__DATA,__mink_custom"
#else
#define CUSTOM_SECTION ".mink.custom"
#endif
extern int ext_counter;

int zeroed[64];
int initialized[16] = {1, 2, 3, 4, 5, 6, 7, 8};
const unsigned char blob[48] = "the quick brown fox jumps over the lazy dog";
const char banner[] = "mink reference corpus";

__attribute__((section(CUSTOM_SECTION), used)) int custom_value = 7;
__attribute__((aligned(64), used)) char aligned_buf[128] = {1};
__attribute__((visibility("hidden"))) int hidden_value = 9;
__attribute__((used)) static int ctor_ran;

int *const pointers[] = {&initialized[0], &initialized[4], &hidden_value, &ext_counter};

__attribute__((constructor)) static void ctor(void)
{
    ctor_ran = 1;
}

int alias_target(void)
{
    return ctor_ran + hidden_value;
}

#ifdef __APPLE__
int alias_name(void)
{
    return alias_target();
}
#else
int alias_name(void) __attribute__((alias("alias_target")));
#endif

int read_pointer(int i)
{
    return *pointers[i & 3] + zeroed[i & 63];
}
