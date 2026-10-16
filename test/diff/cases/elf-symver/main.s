# references to f bare and at version V0, which bind the default and the old definition
    .text
    .globl _start
_start:
    call f
    call f_old
    mov $60, %eax
    syscall
    .symver f_old, f@V0
