/* Standalone state-machine regression, no X server or user input. */
#include <assert.h>
#include <stdio.h>
#include "../keyboard-mode/caps-bridge/normalize.h"
int main(void) {
    struct caps_state a = {0}, b = {0};
    struct key_event out[3];
    assert(caps_normalize(&a, 1, CAPS_KEY, 1, out) == 2);
    assert(out[0].down && !out[1].down && out[0].sym == CAPS_KEY);
    assert(caps_normalize(&a, 1, CAPS_KEY, 0, out) == 0); /* Mac: one tap */
    caps_normalize(&a, 1, 'C', 1, out);
    assert(out[0].sym == 'C'); /* Normal client's case is unchanged. */
    caps_normalize(&a, 1, 'C', 0, out);
    assert(caps_normalize(&a, 1, CAPS_KEY, 1, out) == 2);
    assert(caps_normalize(&a, 1, CAPS_KEY, 1, out) == 0); /* repeat ignored */
    caps_normalize(&a, 1, 'C', 1, out);
    assert(out[0].sym == 'c'); /* iPad: Caps state leaked into letter */
    caps_normalize(&a, 1, 'C', 0, out);
    assert(out[0].sym == 'c');
    assert(caps_normalize(&a, 1, CAPS_KEY, 0, out) == 2); /* iPad: second tap */
    assert(caps_normalize(&a, 1, CAPS_KEY, 1, out) == 2);
    caps_normalize(&a, 1, LEFT_SHIFT, 1, out);
    caps_normalize(&a, 1, 'c', 1, out);
    assert(out[0].sym == 'C'); /* explicit Shift wins, even inverted Caps case */
    caps_normalize(&a, 1, LEFT_SHIFT, 0, out);
    caps_normalize(&a, 1, 'c', 0, out);
    assert(out[0].sym == 'C'); /* release matches its press */
    caps_normalize(&a, 1, '!', 1, out); assert(out[0].sym == '!');
    caps_normalize(&a, 1, 0x1003143, 1, out); assert(out[0].sym == 0x1003143);
    caps_normalize(&b, 1, CAPS_KEY, 1, out);
    assert(caps_normalize(&b, 1, CAPS_KEY, 0, out) == 0); /* per-client state */
    caps_normalize(&a, 1, LEFT_SHIFT, 1, out);
    caps_normalize(&a, 1, RIGHT_SHIFT, 1, out);
    caps_normalize(&a, 1, LEFT_SHIFT, 0, out);
    caps_normalize(&a, 1, 'q', 1, out); assert(out[0].sym == 'Q');
    caps_normalize(&a, 1, RIGHT_SHIFT, 0, out);
    assert(caps_normalize(&a, 0, CAPS_KEY, 0, out) == 1); /* off: exact pass-through */
    assert(out[0].sym == CAPS_KEY && !out[0].down);
    caps_normalize(&a, 0, 'C', 1, out); assert(out[0].sym == 'C');
    caps_normalize(&a, 2, CAPS_KEY, 1, out);
    assert(caps_normalize(&a, 2, CAPS_KEY, 0, out) == 0); /* re-enable resets */
    puts("PASS: Mac pairs, iPad state edges, real Shift, release matching, client isolation, off/reset");
}
