# g at the old version V0, which the reference to g@V0 pulls
    .text
    .globl g_old
g_old:
    lea marker(%rip), %rax
    ret
    .symver g_old, g@V0
    .section .rodata
marker:
    .ascii "PULLED"
