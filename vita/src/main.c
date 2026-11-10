#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <psp2/ctrl.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/sysmem.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/power.h>
#include <psp2/touch.h>

#include "lang.h"
#include "net.h"
#include "ui.h"

#define LOST_AFTER_US 3000000ULL
/* Ahorro de batería: los datos llegan 1 vez por segundo, así que no se dibuja a 60 fps fijos.
 * - Solo se redibuja si algo cambió (datos, botón, estado, reloj) o hay una animación en curso.
 * - Las animaciones van a 30 fps como máximo.
 * - Sin nada que hacer, la app duerme y revisa botones y red 20 veces por segundo. */
#define FRAME_US 33333ULL
#define IDLE_US 50000
#define REDRAW_EVERY_US 1000000ULL /* reloj de la cabecera y paquetes/s del overlay */
#define LERP 0.28f                 /* por frame a 30 fps: mismo ritmo que 0.15 a 60 fps */
/* Sin datos ni botones durante 5 min (PC apagado): se deja que la Vita atenúe y suspenda
 * la pantalla según su configuración, en lugar de mantenerla encendida para nada. */
#define IDLE_SLEEP_US 300000000ULL
#define TOAST_US 2000000ULL

#define VMON_APP_VERSION "1.3"
#define ACK_EVERY_US 1000000ULL   /* respuesta al PC: como mucho 1 por segundo */
#define BATT_EVERY_US 10000000ULL /* la batería cambia despacio: leerla cada 10 s */

/* Pantalla táctil (coordenadas del panel frontal: 1920x1088, el doble que la pantalla) */
#define LONG_PRESS_US 700000ULL /* mantener pulsado: overlay de depuración (como △) */
#define TAP_SLOP 40             /* px de pantalla que puede moverse el dedo en un toque */
#define SWIPE_MIN 200           /* deslizar en horizontal: cambiar idioma (como SELECT) */

static AppState st;

typedef struct {
    int down, moved, long_done;
    int x0, y0, x, y;
    SceUInt64 t0;
} Touch;

/* Gestos: toque = cambiar vista (□), mantener = depuración (△), deslizar = idioma (SELECT).
 * Devuelve 1 si hubo un gesto (hay que redibujar). */
static int touch_update(Touch *t, SceUInt64 now, SceUInt64 *toast_until, SceUInt64 *last_input)
{
    SceTouchData td;
    if (sceTouchPeek(SCE_TOUCH_PORT_FRONT, &td, 1) < 0)
        return 0;
    if (td.reportNum > 0) {
        int x = td.report[0].x / 2, y = td.report[0].y / 2;
        *last_input = now;
        if (!t->down) {
            t->down = 1;
            t->moved = t->long_done = 0;
            t->x0 = t->x = x;
            t->y0 = t->y = y;
            t->t0 = now;
            return 0;
        }
        t->x = x;
        t->y = y;
        if (abs(x - t->x0) > TAP_SLOP || abs(y - t->y0) > TAP_SLOP)
            t->moved = 1;
        if (!t->moved && !t->long_done && now - t->t0 >= LONG_PRESS_US) {
            t->long_done = 1;
            st.debug = !st.debug;
            return 1;
        }
        return 0;
    }
    if (!t->down)
        return 0;
    t->down = 0; /* se levantó el dedo */
    if (t->long_done)
        return 0;
    if (!t->moved) {
        st.compact = !st.compact;
        return 1;
    }
    if (abs(t->x - t->x0) >= SWIPE_MIN && abs(t->x - t->x0) > abs(t->y - t->y0)) {
        lang_next();
        *toast_until = now + TOAST_US;
        return 1;
    }
    return 0;
}

void hist_push(History *h, float v)
{
    h->v[h->head] = v;
    h->head = (h->head + 1) % HIST_LEN;
    if (h->count < HIST_LEN)
        h->count++;
}

/* Acerca *shown a target; devuelve 1 si todavía se está moviendo. */
static int lerp(float *shown, float target)
{
    if (target < 0) /* no disponible: la barra baja a 0 */
        target = 0;
    if (fabsf(target - *shown) < 0.2f) {
        *shown = target;
        return 0;
    }
    *shown += (target - *shown) * LERP;
    return 1;
}

static int animate(void)
{
    int i, moving = 0;
    moving |= lerp(&st.d_cpu, st.stats.cpu);
    moving |= lerp(&st.d_gpu, st.stats.gpu);
    moving |= lerp(&st.d_ram, st.stats.ram);
    for (i = 0; i < st.stats.ncores; i++)
        moving |= lerp(&st.d_cores[i], st.stats.cores[i]);
    return moving;
}

int main(void)
{
    SceCtrlData pad, old;
    SceUInt64 last_rx = 0, last_input, last_draw = 0, pps_t0, ip_t0 = 0, toast_until = 0;
    SceUInt64 last_ack = 0, batt_t0 = 0;
    int got_any = 0, pps_count = 0, dirty = 1, moving = 0, is_tv;
    ConnState prev_conn = CONN_WAITING;
    Touch touch;

    memset(&st, 0, sizeof(st));
    memset(&touch, 0, sizeof(touch));
    vmon_stats_reset(&st.stats);
    memset(&old, 0, sizeof(old));
    st.batt = -1;

    scePowerSetArmClockFrequency(111);
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_DIGITAL);
    sceTouchSetSamplingState(SCE_TOUCH_PORT_FRONT, SCE_TOUCH_SAMPLING_STATE_START);
    is_tv = sceKernelIsPSVitaTV() == 1; /* la PS TV no tiene batería ni pantalla táctil */
    lang_init();
    ui_init();
    st.net_error = net_init();
    pps_t0 = last_input = sceKernelGetProcessTimeWide();

    for (;;) {
        SceUInt64 now = sceKernelGetProcessTimeWide();
        unsigned int pressed;
        int n, toast;

        sceCtrlPeekBufferPositive(0, &pad, 1);
        pressed = pad.buttons & ~old.buttons;
        old = pad;
        if (pad.buttons)
            last_input = now;
        if (pressed)
            dirty = 1;
        if (pressed & SCE_CTRL_START)
            break;
        if (pressed & SCE_CTRL_SQUARE)
            st.compact = !st.compact;
        if (pressed & SCE_CTRL_TRIANGLE)
            st.debug = !st.debug;
        if (pressed & SCE_CTRL_SELECT) {
            lang_next();
            toast_until = now + TOAST_US;
        }
        if (!is_tv && touch_update(&touch, now, &toast_until, &last_input))
            dirty = 1;
        toast = now < toast_until;
        if (toast != st.lang_toast) {
            st.lang_toast = toast;
            dirty = 1;
        }

        if (!got_any && now - ip_t0 >= 1000000ULL) { /* la IP puede aparecer tarde si el WiFi tarda */
            char before[16];
            strncpy(before, net_ip(), sizeof(before) - 1);
            before[sizeof(before) - 1] = '\0';
            net_refresh_ip();
            if (strcmp(before, net_ip()))
                dirty = 1;
            ip_t0 = now;
        }

        n = net_poll(&st.stats, st.last_line, sizeof(st.last_line), st.from_ip, sizeof(st.from_ip));
        if (n > 0) {
            got_any = 1;
            last_rx = now;
            pps_count += n;
            hist_push(&st.h_cpu, st.stats.cpu);
            hist_push(&st.h_gpu, st.stats.gpu);
            hist_push(&st.h_ctemp, st.stats.ctemp);
            hist_push(&st.h_gtemp, st.stats.gtemp);
            dirty = 1;
            if (now - last_ack >= ACK_EVERY_US) { /* avisar al PC de que los datos llegan */
                char ack[64];
                snprintf(ack, sizeof(ack), "VMONACK1;ver=%s;batt=%d;chg=%d", VMON_APP_VERSION, st.batt,
                         st.charging);
                net_reply(ack);
                last_ack = now;
            }
        }

        if (!is_tv && (batt_t0 == 0 || now - batt_t0 >= BATT_EVERY_US)) {
            int b = scePowerGetBatteryLifePercent(), c = scePowerIsBatteryCharging() ? 1 : 0;
            if (b < 0 || b > 100)
                b = -1;
            if (b != st.batt || c != st.charging) {
                st.batt = b;
                st.charging = c;
                dirty = 1;
            }
            batt_t0 = now;
        }
        if (now - pps_t0 >= 1000000ULL) {
            st.pps = pps_count;
            pps_count = 0;
            pps_t0 = now;
        }

        st.conn = !got_any ? CONN_WAITING : (now - last_rx < LOST_AFTER_US ? CONN_OK : CONN_LOST);
        if (st.conn != prev_conn) {
            prev_conn = st.conn;
            dirty = 1;
        }

        /* mantener la pantalla encendida solo mientras sirve para algo */
        if ((got_any && now - last_rx < IDLE_SLEEP_US) || now - last_input < IDLE_SLEEP_US)
            sceKernelPowerTick(SCE_KERNEL_POWER_TICK_DISABLE_AUTO_SUSPEND);

        if (now - last_draw >= REDRAW_EVERY_US)
            dirty = 1;

        if ((dirty || moving) && now - last_draw >= FRAME_US) {
            moving = animate();
            ui_draw(&st, net_ip()); /* espera el vblank */
            last_draw = now;
            dirty = 0;
        } else if (dirty || moving) {
            sceKernelDelayThread((SceUInt)(FRAME_US - (now - last_draw)));
        } else {
            sceKernelDelayThread(IDLE_US);
        }
    }

    net_fini();
    ui_fini();
    lang_fini();
    sceKernelExitProcess(0);
    return 0;
}
