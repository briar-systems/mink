/* thread local storage */
_Thread_local int tls_counter;
_Thread_local int tls_seed = 7;
extern _Thread_local int tls_extern;

int tls_next(void)
{
    tls_counter += tls_seed + tls_extern;
    return tls_counter;
}
