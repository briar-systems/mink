# a bare reference to f, which only a default version defines, and a reference to g at V0
    .text
    .globl _start
_start:
    call f
    call g_old
    mov $60, %eax
    syscall
    .symver g_old, g@V0
