# a 32-bit absolute reference to an imported function
    .text
    .globl main
main:
    movl $func, %eax
    ret
