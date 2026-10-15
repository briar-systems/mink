// a page pair to a global in a position independent executable
    .text
    .globl _start
_start:
    adrp x0, target
    add x0, x0, :lo12:target
    ret
    .data
    .globl target
target:
    .quad 7
