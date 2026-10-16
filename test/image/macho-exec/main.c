/* adrp and ldr with an addend reach table[1], and pointer is an absolute
   pointer the loader rebases */
int table[4] = {1, 2, 3, 4};
int *pointer = &table[2];
int main(void) { return table[1] + *pointer - 5; }
