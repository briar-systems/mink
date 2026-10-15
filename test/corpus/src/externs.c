/* definitions of what basic.c, data.c and tls.c import, for images whose
   linker will not leave a thread-local import to dynamic lookup */
int ext_counter;
_Thread_local int tls_extern;

int ext_call(int x)
{
    return x + ext_counter;
}
