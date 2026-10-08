	.text
	.globl	f
f:
	call	g
	.p2align 4
	addi	a0, a0, 1
	ret
	.globl	g
g:
	ret
