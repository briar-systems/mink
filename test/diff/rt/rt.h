/* the runtime of the differential programs: no C library, a line written to
   standard output and an exit status, over the linux system call or, for a
   freestanding image under qemu-system, the virt machine's UART and test device */

long rt_write(const char *text, long len);
long rt_text(const char *text);
long rt_number(long n);
int program(void);
