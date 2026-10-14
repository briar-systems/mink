# a 32-bit absolute reference to a symbol a dylib binds
    .section __DATA,__data
    .p2align 2
cell:
    .long _imported
    .text
    .globl _main
_main:
    ret
