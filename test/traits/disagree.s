# a build attribute that sets BTI in a file without the GNU property note,
# which states it clear
.aeabi_subsection aeabi_feature_and_bits, optional, uleb128
.aeabi_attribute Tag_Feature_BTI, 1
.aeabi_attribute Tag_Feature_PAC, 0
.aeabi_attribute Tag_Feature_GCS, 0

.text
.globl f
f:
    ret
