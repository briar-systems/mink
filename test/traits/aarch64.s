# branch protection stated both ways, as clang states it: the GNU property
# note sets BTI and GCS, and the buildattr64 subsections set the same and
# state pointer authentication platform 1, version 5
.aeabi_subsection aeabi_pauthabi, required, uleb128
.aeabi_attribute Tag_PAuth_Platform, 1
.aeabi_attribute Tag_PAuth_Schema, 5
.aeabi_subsection aeabi_feature_and_bits, optional, uleb128
.aeabi_attribute Tag_Feature_BTI, 1
.aeabi_attribute Tag_Feature_PAC, 0
.aeabi_attribute Tag_Feature_GCS, 1

.section .note.gnu.property, "a", @note
.p2align 3
.word 4
.word 16
.word 5
.asciz "GNU"
.word 0xc0000000
.word 4
.word 5
.word 0

.text
.globl f
f:
    bti c
    ret
