/* data of every kind: bss, rodata, custom and aligned sections, constructors */
extern int ext_counter;

int zeroed[64];
int initialized[16] = {1, 2, 3, 4, 5, 6, 7, 8};
const unsigned char blob[48] = "the quick brown fox jumps over the lazy dog";
const char banner[] = "mink reference corpus";

__attribute__((section(".mink.custom"), used)) int custom_value = 7;
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

int alias_name(void) __attribute__((alias("alias_target")));

int read_pointer(int i)
{
    return *pointers[i & 3] + zeroed[i & 63];
}
