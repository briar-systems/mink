/* the gate of the WASI lane: two functions and one indirect call, linked
   into a module with no entry */
typedef int (*fn)(int);
fn volatile slot;
__attribute__((noinline)) static int twice(int x) { return x * 2; }
__attribute__((export_name("run"))) int run(int x) { slot = twice; return slot(x); }
