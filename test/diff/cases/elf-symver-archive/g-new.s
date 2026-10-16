# g at the default version V1, which the reference to g@V0 leaves in the archive
    .text
    .globl g_new
g_new:
    lea marker(%rip), %rax
    ret
    .symver g_new, g@@V1
    .section .rodata
marker:
    .ascii "PULLED"
