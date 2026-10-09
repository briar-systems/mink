# compressed code beside double-float code, as masc's builder emits it
.text
.globl f
f:
    c.addi a0, 1
    c.li a1, 3
    fadd.d fa0, fa0, fa1
    c.jr ra
