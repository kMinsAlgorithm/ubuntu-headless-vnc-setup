/* No text is logged. State belongs to one authenticated RFB client. */
#ifndef VNC_CAPS_NORMALIZE_H
#define VNC_CAPS_NORMALIZE_H
#include <stdint.h>
#include <string.h>
#define CAPS_KEY 0xffe5u
#define LEFT_SHIFT 0xffe1u
#define RIGHT_SHIFT 0xffe2u
struct caps_state {
    unsigned caps_down, latched, shift;
    uint32_t generation;
    uint32_t latin_down[26];
};
struct key_event { uint32_t sym; int down; };

/* A normal client sends down/up for one Caps press. RVNC iPad sends the
 * lock state: down, letters, up, letters. Seeing a non-modifier while Caps
 * is held identifies the latter. Once identified, both edges are taps.
 * A Mac that deliberately holds Caps while typing also opts into this
 * no-uppercase-lock behavior. Shift remains an independent real key. */
static int caps_normalize(struct caps_state *s, uint32_t generation,
                          uint32_t sym, int down, struct key_event out[3]) {
    int index = -1;
    if (s->generation != generation) {
        memset(s, 0, sizeof(*s));
        s->generation = generation;
    }
    if (!generation) {
        out[0] = (struct key_event){sym, down};
        return 1;
    }
    if (sym == LEFT_SHIFT || sym == RIGHT_SHIFT) {
        unsigned bit = sym == LEFT_SHIFT ? 1u : 2u;
        if (down) s->shift |= bit; else s->shift &= ~bit;
    }
    if (sym == CAPS_KEY) {
        int emit = 0;
        if (down) {
            emit = !s->caps_down;
            s->caps_down = 1;
        } else {
            emit = s->latched && s->caps_down;
            s->caps_down = 0;
        }
        if (!emit) return 0;
        out[0] = (struct key_event){CAPS_KEY, 1};
        out[1] = (struct key_event){CAPS_KEY, 0};
        return 2;
    }
    /* X11 modifiers: Shift_L through Hyper_R, Mode_switch, ISO_Level3_Shift. */
    if (down && s->caps_down && !(sym >= 0xffe1 && sym <= 0xffee)
            && sym != 0xff7e && sym != 0xfe03) s->latched = 1;
    if (sym >= 'A' && sym <= 'Z') index = (int)(sym - 'A');
    if (sym >= 'a' && sym <= 'z') index = (int)(sym - 'a');
    if (index >= 0) {
        if (!down && s->latin_down[index]) {
            sym = s->latin_down[index];
            s->latin_down[index] = 0;
        } else if (down) {
            if (s->latched && s->caps_down)
                sym = (uint32_t)((s->shift ? 'A' : 'a') + index);
            s->latin_down[index] = sym;
        }
    }
    out[0] = (struct key_event){sym, down};
    return 1;
}
#endif
