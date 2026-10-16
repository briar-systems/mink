/* entries a link may merge: strings of 1, 2 and 4 byte elements and constants of 4, 8, 16 and 32 bytes */
typedef __CHAR16_TYPE__ char16;
typedef __CHAR32_TYPE__ char32;
typedef float vec4 __attribute__((vector_size(16)));
typedef float vec8 __attribute__((vector_size(32)));

const char *narrow(void)
{
    return "a narrow string";
}

const char16 *wide(void)
{
    return u"a wide string";
}

const char32 *wider(void)
{
    return U"a wider string";
}

float scale4(float x)
{
    return x * 3.14159f;
}

double scale8(double x)
{
    return x * 2.718281828459045;
}

vec4 scale16(vec4 x)
{
    vec4 k = {1.1f, 2.2f, 3.3f, 4.4f};
    return x * k;
}

#if defined(__x86_64__) || defined(__i386__)
__attribute__((target("avx"))) void scale32(vec8 *x)
{
    vec8 k = {1.1f, 2.2f, 3.3f, 4.4f, 5.5f, 6.6f, 7.7f, 8.8f};
    *x = *x * k;
}
#endif
