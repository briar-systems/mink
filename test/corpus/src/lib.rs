#![no_std]

#[no_mangle]
pub static GREETING: [u8; 16] = *b"mink corpus rust";

#[no_mangle]
pub extern "C" fn fold(values: *const u32, count: usize) -> u32 {
    let mut acc = 0u32;
    let mut i = 0;
    while i < count {
        acc = acc.rotate_left(5) ^ unsafe { *values.add(i) };
        i += 1;
    }
    acc
}

#[no_mangle]
pub extern "C" fn checked_add(a: u64, b: u64) -> u64 {
    a.checked_add(b).unwrap_or(u64::MAX)
}

#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    loop {}
}
