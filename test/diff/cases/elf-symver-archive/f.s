# f at the default version V1, which the bare reference pulls
    .text
    .globl f_new
f_new:
    lea marker(%rip), %rax
    ret
    .symver f_new, f@@V1
    .section .rodata
marker:
    .ascii "PULLED"
