/* functions, relocations against externals, a jump table and float constants */
extern int ext_counter;
extern int ext_call(int);

int global_init = 42;
static int local_state;
const char *const names[] = {"alpha", "beta", "gamma", "delta"};
int (*const table[])(int) = {ext_call, 0};

__attribute__((weak)) int weak_hook(int x)
{
    return x + 1;
}

int sum(const int *v, int n)
{
    int total = 0;
    for (int i = 0; i < n; i++)
        total += v[i];
    local_state += total;
    return total + ext_counter;
}

int dispatch(int i, int x)
{
    switch (i) {
    case 0: return x + 3;
    case 1: return x * 5;
    case 2: return ext_call(x);
    case 3: return x - 7;
    case 4: return weak_hook(x);
    case 5: return x ^ 0x55;
    default: return -1;
    }
}

long long mul64(long long a, long long b)
{
    return a * b + local_state;
}

double scale(double x)
{
    return x * 1.5 + 0.25;
}

const char *name_of(int i)
{
    return names[i & 3];
}
