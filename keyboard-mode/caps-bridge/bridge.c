/* Small opt-in adapter for the installed libvncserver ABI. No input logging. */
#define _GNU_SOURCE
#include <rfb/rfb.h>
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include "normalize.h"

struct client_state {
    rfbClientPtr client;
    ClientGoneHookPtr gone;
    struct caps_state keys;
    struct client_state *next;
};
static struct client_state *clients;
static rfbKbdAddEventProcPtr original_keyboard;
static Display *control_display;
static Atom mode_atom;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;

static void client_gone(rfbClientPtr client) {
    ClientGoneHookPtr original = NULL;
    struct client_state **link, *item;
    pthread_mutex_lock(&mutex);
    for (link = &clients; (item = *link); link = &item->next) {
        if (item->client == client) {
            original = item->gone;
            *link = item->next;
            free(item);
            break;
        }
    }
    pthread_mutex_unlock(&mutex);
    if (original) original(client);
}

static uint32_t mode_generation(void) {
    Atom type;
    int format;
    unsigned long count, after, value = 0;
    unsigned char *data = NULL;
    if (XGetWindowProperty(control_display, DefaultRootWindow(control_display),
            mode_atom, 0, 1, False, XA_CARDINAL, &type, &format,
            &count, &after, &data) == Success && type == XA_CARDINAL
            && format == 32 && count == 1 && after == 0 && data)
        value = *(unsigned long *)data;
    if (data) XFree(data);
    return (uint32_t)value;
}

static void normalized_keyboard(rfbBool down, rfbKeySym sym, rfbClientPtr client) {
    struct client_state *item;
    struct key_event events[3];
    int count, i;
    pthread_mutex_lock(&mutex);
    for (item = clients; item && item->client != client; item = item->next) {}
    if (!item) {
        item = calloc(1, sizeof(*item));
        if (!item) {
            pthread_mutex_unlock(&mutex);
            original_keyboard(down, sym, client);
            return;
        }
        item->client = client;
        item->gone = client->clientGoneHook;
        client->clientGoneHook = client_gone;
        item->next = clients;
        clients = item;
    }
    count = caps_normalize(&item->keys, mode_generation(), sym, down, events);
    /* Keep one client's emitted Caps down/up together. No pointer/clipboard,
     * authentication, or framebuffer callbacks are replaced. */
    for (i = 0; i < count; i++)
        original_keyboard(events[i].down, events[i].sym, client);
    pthread_mutex_unlock(&mutex);
}

/* This exact symbol is imported by Ubuntu's installed x11vnc. */
void rfbInitServerWithPthreadsAndZRLE(rfbScreenInfoPtr screen) {
    void (*original_init)(rfbScreenInfoPtr) = dlsym(RTLD_NEXT,
            "rfbInitServerWithPthreadsAndZRLE");
    unsigned long identity[2] = {(unsigned long)getpid(), 1};
    unsigned long off = 0;
    Atom identity_atom;
    if (!original_init) { fputs("VNC Caps bridge: incompatible library\n", stderr); abort(); }
    original_init(screen);
    if (original_keyboard || !screen->kbdAddEvent) return;
    control_display = XOpenDisplay(NULL);
    if (!control_display) {
        fputs("VNC Caps bridge: control display unavailable; keyboard unchanged\n", stderr);
        return;
    }
    mode_atom = XInternAtom(control_display, "_VNC_KEYBOARD_CAPS_MODE", False);
    identity_atom = XInternAtom(control_display, "_VNC_KEYBOARD_CAPS_BRIDGE", False);
    XChangeProperty(control_display, DefaultRootWindow(control_display), mode_atom,
                    XA_CARDINAL, 32, PropModeReplace, (unsigned char *)&off, 1);
    XChangeProperty(control_display, DefaultRootWindow(control_display), identity_atom,
                    XA_CARDINAL, 32, PropModeReplace, (unsigned char *)identity, 2);
    XSync(control_display, False);
    original_keyboard = screen->kbdAddEvent;
    screen->kbdAddEvent = normalized_keyboard;
    fputs("VNC Caps bridge ready (disabled until keyboard mode is enabled)\n", stderr);
}
