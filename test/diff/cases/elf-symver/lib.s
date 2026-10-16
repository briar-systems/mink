# f defined at the default version V1 and at the old version V0
    .text
    .globl f_new, f_old
f_new:
    mov $2, %eax
    ret
f_old:
    mov $1, %eax
    ret
    .symver f_new, f@@V1
    .symver f_old, f@V0
