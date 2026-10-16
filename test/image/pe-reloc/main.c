/* the entry returns the value an absolute data pointer reaches, so the image
   needs a base relocation and imports nothing */
int value = 42;
int *pointer = &value;

int mainCRTStartup(void) {
    return *pointer;
}
