# a pointer to a symbol a dylib binds, in a read-only section
    .section __TEXT,__const
    .p2align 3
cell:
    .quad _imported
    .text
    .globl _main
_main:
    ret
