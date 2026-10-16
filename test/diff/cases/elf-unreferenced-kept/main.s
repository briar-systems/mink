# an entry and a read-only section nothing refers to
	.section .text._start,"ax",@progbits
	.globl _start
_start:
	movl $60, %eax
	xorl %edi, %edi
	syscall

	.section .rodata.unreferenced,"a",@progbits
	.ascii "UNREFERENCED"
