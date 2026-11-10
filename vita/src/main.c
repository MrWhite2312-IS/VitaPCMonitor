#include <string.h>

#include <psp2/ctrl.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/power.h>

#include "net.h"
#include "ui.h"

#define LOST_AFTER_US 3000000ULL
#define LERP 0.15f

static AppState st;

void hist_push(History *h, float v)
{
    h->v[h->head] = v;
    h->head = (h->head + 1) % HIST_LEN;
    if (h->count < HIST_LEN)
        h->count++;
}

static void lerp(float *shown, float target)
{
    if (target < 0) /* no disponible: la barra baja a 0 */
        target = 0;
    *shown += (target - *shown) * LERP;
}

int main(void)
{
    SceCtrlData pad, old;
    SceUInt64 last_rx = 0, pps_t0;
    int got_any = 0, pps_count = 0, frame = 0, i;

    memset(&st, 0, sizeof(st));
    vmon_stats_reset(&st.stats);
    memset(&old, 0, sizeof(old));

    scePowerSetArmClockFrequency(111);
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_DIGITAL);
    ui_init();
    st.net_error = net_init();
    pps_t0 = sceKernelGetProcessTimeWide();

    for (;;) {
        SceUInt64 now = sceKernelGetProcessTimeWide();
        unsigned int pressed;
        int n;

        sceKernelPowerTick(SCE_KERNEL_POWER_TICK_DISABLE_AUTO_SUSPEND);

        sceCtrlPeekBufferPositive(0, &pad, 1);
        pressed = pad.buttons & ~old.buttons;
        old = pad;
        if (pressed & SCE_CTRL_START)
            break;
        if (pressed & SCE_CTRL_SQUARE)
            st.compact = !st.compact;
        if (pressed & SCE_CTRL_TRIANGLE)
            st.debug = !st.debug;

        if (frame++ % 60 == 0 && !got_any) /* la IP puede aparecer tarde si el WiFi tarda */
            net_refresh_ip();

        n = net_poll(&st.stats, st.last_line, sizeof(st.last_line), st.from_ip, sizeof(st.from_ip));
        if (n > 0) {
            got_any = 1;
            last_rx = now;
            pps_count += n;
            hist_push(&st.h_cpu, st.stats.cpu);
            hist_push(&st.h_gpu, st.stats.gpu);
            hist_push(&st.h_ctemp, st.stats.ctemp);
            hist_push(&st.h_gtemp, st.stats.gtemp);
        }
        if (now - pps_t0 >= 1000000ULL) {
            st.pps = pps_count;
            pps_count = 0;
            pps_t0 = now;
        }

        st.conn = !got_any ? CONN_WAITING : (now - last_rx < LOST_AFTER_US ? CONN_OK : CONN_LOST);

        lerp(&st.d_cpu, st.stats.cpu);
        lerp(&st.d_gpu, st.stats.gpu);
        lerp(&st.d_ram, st.stats.ram);
        for (i = 0; i < st.stats.ncores; i++)
            lerp(&st.d_cores[i], st.stats.cores[i]);

        ui_draw(&st, net_ip());
    }

    net_fini();
    ui_fini();
    sceKernelExitProcess(0);
    return 0;
}
