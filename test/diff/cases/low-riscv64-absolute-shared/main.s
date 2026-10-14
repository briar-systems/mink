# an absolute pair to a local in a shared library
    .text
    .globl entry
entry:
    lui a0, %hi(target)
    addi a0, a0, %lo(target)
    ret
    .data
    .hidden target
    .globl target
target:
    .quad 7
