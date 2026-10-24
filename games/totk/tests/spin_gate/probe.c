/* CPU only, against the real runtime/threads.c (Breath of the Wild): which loops the spin gate takes for spin waits
   (issue #480). The scan runs over a synthetic module of A64 code, so no game file is needed:
     spin1  ldr / cmp / b.eq                     1.9.0's spin lock at main+0xef635c           a spin wait
     spin2  ldaxr / cbz out / clrex / b          its exclusive retry at main+0xef6368         a spin wait
     cas    clrex / ldr / add / ldaxr / cmp / b.ne  a compare-and-swap retry                   a spin wait
     store  ldr / str / cbz                      writes memory                                not one
     count  add w0 / cmp / b.ne                  ends by itself (a register it reads)         not one
     walk   ldr x0, [x0] / cbnz                  a list walk (the same)                       not one
     call   ldr / bl / cbz                       calls                                        not one
     time   mrs cntvct / cmp / b.lo              reads the clock: a timed wait ends by itself not one
     wb     ldr w1, [x2], #4 / cbz               post-index writeback                         not one
   Build and run from games/totk: make probe-spin-gate. Negative control: TOTK_SPIN_GATE=0 must find no loop. */
#include "../../runtime/threads.c"
#include <mach/mach_time.h>

_Noreturn void runtime_fail(const char *message) { fprintf(stderr, "FAIL %s\n", message); exit(1); }
void runtime_thread_init(void) {}
uint64_t runtime_now_ns(void) { mach_timebase_info_data_t t; mach_timebase_info(&t); return (uint64_t)((__uint128_t)mach_absolute_time() * t.numer / t.denom); }
uint64_t runtime_hle_tsd_off;
int runtime_guest_code_pc(uint64_t pc) { (void)pc; return 0; }
void *runtime_symbol(const char *name) { (void)name; return NULL; }

static const uint32_t code[] = {
    0xd503201f,                                       /* 0x00 nop (the scan starts at the second word) */
    0xb940012e, 0x710005df, 0x54ffffc0,               /* 0x04 spin1 */
    0x885ffd2e, 0x3400032e, 0xd5033f5f, 0x17fffffd,   /* 0x10 spin2 */
    0xb9400041, 0xb9000061, 0x34ffffc1,               /* 0x20 store */
    0x11000400, 0x7100281f, 0x54ffffc1,               /* 0x2c count */
    0xf9400000, 0xb5ffffe0,                           /* 0x38 walk */
    0xb9400041, 0x9400000d, 0x34ffffc1,               /* 0x40 call */
    0xd53be041, 0xeb02003f, 0x54ffffc3,               /* 0x4c time */
    0xb8404441, 0x34ffffe1,                           /* 0x58 wb */
    0xd5033f5f, 0xb940010a, 0x1100054d, 0x885ffd0d, 0x6b0a01bf, 0x54ffff61,   /* 0x60 cas */
    0xd65f03c0,                                       /* 0x78 ret */
};
int runtime_module_text(unsigned i, const uint8_t **base, uint64_t *text_end, const char **name) {
    if (i) return 0;
    *base = (const uint8_t *)code; *text_end = sizeof code; *name = "test"; return 1;
}

int main(void) {
    static const struct { const char *name; unsigned lo, hi; int spin; } loops[] = {
        {"spin1", 0x04, 0x0c, 1}, {"spin2", 0x10, 0x1c, 1}, {"cas", 0x60, 0x74, 1}, {"store", 0x20, 0x28, 0},
        {"count", 0x2c, 0x34, 0}, {"walk", 0x38, 0x3c, 0}, {"call", 0x40, 0x48, 0}, {"time", 0x4c, 0x54, 0}, {"wb", 0x58, 0x5c, 0},
    };
    const char *e = getenv("TOTK_SPIN_GATE"); int off = e && !strcmp(e, "0");
    pthread_mutex_lock(&G); spin_gate_on(); pthread_mutex_unlock(&G);
    uint64_t b = (uintptr_t)code; int bad = 0;
    for (unsigned i = 0; i < sizeof loops / sizeof *loops; i++) {
        int want = loops[i].spin && !off;
        for (unsigned a = loops[i].lo; a <= loops[i].hi; a += 4)
            if (spin_gate_pc(b + a) != want) { fprintf(stderr, "FAIL %s at +%#x: %s\n", loops[i].name, a, want ? "not taken for a spin wait" : "taken for a spin wait"); bad = 1; }
    }
    if (spin_gate_pc(b) || spin_gate_pc(b + 0x78)) { fprintf(stderr, "FAIL code outside the loops taken for a spin wait\n"); bad = 1; }
    printf("{\"status\":\"%s\",\"ranges\":%u,\"gate\":\"%s\"}\n", bad ? "fail" : "pass", g_spin_nranges, off ? "off" : "on");
    return bad;
}
