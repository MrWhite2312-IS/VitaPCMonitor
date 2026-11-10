#include <math.h>
#include <string.h>

#include <psp2/ctrl.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/power.h>

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

static AppState st;

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
    int got_any = 0, pps_count = 0, dirty = 1, moving = 0;
    ConnState prev_conn = CONN_WAITING;

    memset(&st, 0, sizeof(st));
    vmon_stats_reset(&st.stats);
    memset(&old, 0, sizeof(old));

    scePowerSetArmClockFrequency(111);
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_DIGITAL);
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
