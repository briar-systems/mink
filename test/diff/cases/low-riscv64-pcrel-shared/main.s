# a pc-relative pair to a local in a shared library
    .text
    .globl entry
entry:
1:  auipc a0, %pcrel_hi(target)
    addi a0, a0, %pcrel_lo(1b)
    ret
    .data
    .hidden target
    .globl target
target:
    .quad 7
