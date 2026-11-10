#include "ui.h"

#include <stdio.h>
#include <string.h>

#include <psp2/rtc.h>
#include <vita2d.h>

#include "lang.h"
#include "net.h"

#define SCREEN_W 960
#define SCREEN_H 544

static vita2d_pgf *font;
static int dim; /* "Sin señal": todo lo dibujado se atenúa */

static unsigned int rgb(unsigned int r, unsigned int g, unsigned int b)
{
    if (dim) {
        r = r * 45 / 100;
        g = g * 45 / 100;
        b = b * 45 / 100;
    }
    return RGBA8(r, g, b, 255);
}

#define C_BG RGBA8(0x10, 0x14, 0x18, 0xFF)
#define C_PANEL rgb(0x1B, 0x21, 0x28)
#define C_TRACK rgb(0x2A, 0x32, 0x3C)
#define C_TEXT rgb(0xE6, 0xEA, 0xEE)
#define C_MUTED rgb(0x8A, 0x94, 0x9E)
#define C_GREEN rgb(0x3C, 0xC8, 0x6E)
#define C_AMBER rgb(0xF0, 0xB4, 0x28)
#define C_RED rgb(0xE8, 0x48, 0x48)
#define C_LINE_PCT rgb(0x4A, 0x9E, 0xFF)
#define C_LINE_TEMP rgb(0xFF, 0x8C, 0x42)

static unsigned int pct_color(float v)
{
    return v > 85 ? C_RED : v >= 60 ? C_AMBER : C_GREEN;
}

static unsigned int temp_color(float t)
{
    if (t < 0)
        return C_MUTED;
    return t > 85 ? C_RED : t >= 70 ? C_AMBER : C_GREEN;
}

static void text(int x, int y, unsigned int c, float s, const char *t)
{
    vita2d_pgf_draw_text(font, x, y, c, s, t);
}

static void text_right(int right_x, int y, unsigned int c, float s, const char *t)
{
    text(right_x - vita2d_pgf_text_width(font, s, t), y, c, s, t);
}

static void text_center(int cx, int y, unsigned int c, float s, const char *t)
{
    text(cx - vita2d_pgf_text_width(font, s, t) / 2, y, c, s, t);
}

/* Dibuja t recortado con ".." si no cabe en max_w píxeles. */
static void text_fit(int x, int y, int max_w, unsigned int c, float s, const char *t)
{
    char b[64];
    int n;
    if (vita2d_pgf_text_width(font, s, t) <= max_w) {
        text(x, y, c, s, t);
        return;
    }
    n = (int)strlen(t);
    if (n > (int)sizeof(b) - 3)
        n = (int)sizeof(b) - 3;
    do {
        n--;
        while (n > 0 && ((unsigned char)t[n] & 0xC0) == 0x80) /* no cortar un carácter UTF-8 */
            n--;
        memcpy(b, t, n);
        memcpy(b + n, "..", 3);
    } while (n > 0 && vita2d_pgf_text_width(font, s, b) > max_w);
    text(x, y, c, s, b);
}

/* -1 => "--" */
static const char *fmtv(char *buf, size_t n, const char *fmt, float v)
{
    if (v < 0)
        snprintf(buf, n, "--");
    else
        snprintf(buf, n, fmt, v);
    return buf;
}

static void bar(int x, int y, int w, int h, float shown)
{
    float f = shown < 0 ? 0 : shown > 100 ? 100 : shown;
    vita2d_draw_rectangle(x, y, w, h, C_TRACK);
    vita2d_draw_rectangle(x, y, w * f / 100.0f, h, pct_color(f));
}

static float hist_at(const History *h, int i) /* i = 0 es la muestra más vieja */
{
    return h->v[(h->head - h->count + i + HIST_LEN) % HIST_LEN];
}

static void plot(int x, int y, int w, int h, const History *hist, float lo, float hi, unsigned int c)
{
    int i;
    float step = (float)w / (HIST_LEN - 1);
    int x0 = x + w - (int)((hist->count - 1) * step); /* lo más nuevo pegado a la derecha */
    for (i = 1; i < hist->count; i++) {
        float a = hist_at(hist, i - 1), b = hist_at(hist, i);
        float ya, yb;
        if (a < 0 || b < 0)
            continue;
        a = a < lo ? lo : a > hi ? hi : a;
        b = b < lo ? lo : b > hi ? hi : b;
        ya = y + h - (a - lo) / (hi - lo) * h;
        yb = y + h - (b - lo) / (hi - lo) * h;
        vita2d_draw_line(x0 + (i - 1) * step, ya, x0 + i * step, yb, c);
    }
}

static void graph(int x, int y, int w, int h, const History *pct, const History *temp)
{
    int i;
    vita2d_draw_rectangle(x, y, w, h, C_BG);
    for (i = 1; i < 4; i++)
        vita2d_draw_line(x, y + h * i / 4, x + w, y + h * i / 4, C_TRACK);
    plot(x, y, w, h, pct, 0, 100, C_LINE_PCT);
    plot(x, y, w, h, temp, 30, 100, C_LINE_TEMP);
    text(x + 6, y + 16, C_LINE_PCT, 0.7f, "% 0-100");
    text(x + 80, y + 16, C_LINE_TEMP, 0.7f, "°C 30-100");
    text_right(x + w - 6, y + h - 6, C_MUTED, 0.7f, "60 s");
}

static void panel_head(int x, int y, int w, const char *title, const char *model, float shown, float pct,
                       float temp)
{
    char b[32];
    int bw = w - 32 - 160;
    vita2d_draw_rectangle(x, y, w, 334, C_PANEL);
    text(x + 16, y + 30, C_TEXT, 1.1f, title);
    text_fit(x + 70, y + 30, x + w - 16 - (x + 70), C_MUTED, 1.0f, model);
    bar(x + 16, y + 46, bw, 24, shown);
    text(x + 16 + bw + 12, y + 67, C_TEXT, 1.1f, fmtv(b, sizeof(b), "%.0f%%", pct));
    if (temp >= 0)
        snprintf(b, sizeof(b), "%.0f°C", temp);
    else
        snprintf(b, sizeof(b), "--°C");
    text_right(x + w - 16, y + 67, temp_color(temp), 1.1f, b);
}

static void draw_cpu(const AppState *st, int x, int y, int w)
{
    const VmonStats *s = &st->stats;
    int i, n = s->ncores;
    panel_head(x, y, w, "CPU", s->cpu_name, st->d_cpu, s->cpu, s->ctemp);
    if (n > 0) {
        int gap = 4, cw = (w - 32 - gap * (n - 1)) / n, top = y + 86, h = 60;
        for (i = 0; i < n; i++) {
            float f = st->d_cores[i] < 0 ? 0 : st->d_cores[i] > 100 ? 100 : st->d_cores[i];
            int bx = x + 16 + i * (cw + gap), fh = (int)(h * f / 100.0f);
            vita2d_draw_rectangle(bx, top, cw, h, C_TRACK);
            vita2d_draw_rectangle(bx, top + h - fh, cw, fh, pct_color(f));
        }
    } else {
        text(x + 16, y + 120, C_MUTED, 0.9f, tr(S_NO_THREAD_DATA));
    }
    graph(x + 16, y + 160, w - 32, 158, &st->h_cpu, &st->h_ctemp);
}

static void draw_gpu(const AppState *st, int x, int y, int w)
{
    const VmonStats *s = &st->stats;
    char b[64], u[16], t[16];
    panel_head(x, y, w, "GPU", s->gpu_name, st->d_gpu, s->gpu, s->gtemp);
    snprintf(b, sizeof(b), "VRAM %s / %s GB", fmtv(u, sizeof(u), "%.1f", s->vramu),
             fmtv(t, sizeof(t), "%.1f", s->vramt));
    text(x + 16, y + 118, C_TEXT, 1.0f, b);
    snprintf(b, sizeof(b), "%s MHz", fmtv(u, sizeof(u), "%.0f", s->gclk));
    text_right(x + w - 16, y + 118, C_TEXT, 1.0f, b);
    graph(x + 16, y + 160, w - 32, 158, &st->h_gpu, &st->h_gtemp);
}

static void draw_bottom(const AppState *st)
{
    const VmonStats *s = &st->stats;
    char b[96], u[16], t[16], p[16];
    int lx, dx;
    vita2d_draw_rectangle(12, 394, 936, 138, C_PANEL);

    text(28, 432, C_TEXT, 1.1f, "RAM");
    bar(100, 412, 460, 26, st->d_ram);
    snprintf(b, sizeof(b), "%s / %s GB (%s)", fmtv(u, sizeof(u), "%.1f", s->ramu),
             fmtv(t, sizeof(t), "%.1f", s->ramt), fmtv(p, sizeof(p), "%.0f%%", s->ram));
    text(580, 432, C_TEXT, 1.1f, b);

    /* las etiquetas cambian de largo según el idioma: los valores se corren si hace falta */
    text(28, 494, C_TEXT, 1.1f, tr(S_NET));
    lx = 28 + vita2d_pgf_text_width(font, 1.1f, tr(S_NET)) + 14;
    if (lx < 100)
        lx = 100;
    snprintf(b, sizeof(b), tr(S_UP), fmtv(u, sizeof(u), "%.0f", s->up));
    text(lx, 494, C_TEXT, 1.0f, b);
    snprintf(b, sizeof(b), tr(S_DOWN), fmtv(u, sizeof(u), "%.0f", s->down));
    text(lx + 230, 494, C_TEXT, 1.0f, b);
    text(580, 494, C_TEXT, 1.1f, tr(S_DISK));
    dx = 580 + vita2d_pgf_text_width(font, 1.1f, tr(S_DISK)) + 14;
    if (dx < 670)
        dx = 670;
    text(dx, 494, s->disk < 0 ? C_MUTED : pct_color(s->disk), 1.1f, fmtv(b, sizeof(b), "%.0f%%", s->disk));
}

/* Icono de pila + porcentaje, alineado a la derecha en right_x. Verde/ámbar/rojo según la carga;
 * azul mientras carga. */
static void draw_battery(int right_x, int pct, int charging)
{
    char b[8];
    int tw, x, fill;
    unsigned int c = charging ? C_LINE_PCT : pct <= 15 ? C_RED : pct <= 30 ? C_AMBER : C_GREEN;
    snprintf(b, sizeof(b), "%d%%", pct);
    tw = vita2d_pgf_text_width(font, 0.9f, b);
    text(right_x - tw, 29, C_MUTED, 0.9f, b);
    x = right_x - tw - 8 - 30; /* cuerpo 26x13 + polo 3x6 */
    vita2d_draw_rectangle(x, 16, 26, 13, C_TRACK);
    vita2d_draw_rectangle(x + 26, 19, 3, 7, C_TRACK);
    fill = 22 * pct / 100;
    vita2d_draw_rectangle(x + 2, 18, fill < 1 ? 1 : fill, 9, c);
}

static void draw_header(const AppState *st)
{
    char b[16];
    const char *label;
    unsigned int c;
    SceDateTime now;
    int tx;

    text(16, 30, C_TEXT, 1.1f, st->stats.host[0] ? st->stats.host : "VitaMon");

    sceRtcGetCurrentClockLocalTime(&now);
    snprintf(b, sizeof(b), "%02d:%02d", now.hour, now.minute);
    text_right(SCREEN_W - 16, 30, C_TEXT, 1.1f, b);

    if (st->conn == CONN_OK) {
        label = tr(S_CONNECTED);
        c = C_GREEN;
    } else if (st->conn == CONN_LOST) {
        label = tr(S_LOST);
        c = RGBA8(0xE8, 0x48, 0x48, 0xFF);
    } else {
        label = tr(S_WAITING);
        c = C_AMBER;
    }
    tx = SCREEN_W - 100 - vita2d_pgf_text_width(font, 1.0f, label);
    vita2d_draw_fill_circle(tx - 14, 23, 6, c);
    text(tx, 30, c, 1.0f, label);

    /* batería de la Vita, a la izquierda del estado */
    if (st->batt >= 0)
        draw_battery(tx - 34, st->batt, st->charging);

    /* FPS del juego en el PC, en el centro (solo si hay un juego en primer plano) */
    if (st->conn == CONN_OK && st->stats.fps >= 0) {
        char f[24];
        snprintf(f, sizeof(f), "%.0f FPS", st->stats.fps);
        text_center(SCREEN_W / 2, 31, C_LINE_PCT, 1.3f, f);
    }
}

static void draw_waiting(const AppState *st, const char *ip)
{
    char b[96];
    int cx = SCREEN_W / 2;
    text_center(cx, 170, C_TEXT, 2.0f, tr(S_WAITING_DATA));
    if (net_error_text()[0]) {
        snprintf(b, sizeof(b), "%s %s", st->net_error ? tr(S_NET_ERROR) : tr(S_NOTICE), net_error_text());
        text_center(cx, 230, st->net_error ? C_RED : C_AMBER, 1.1f, b);
    }
    snprintf(b, sizeof(b), tr(S_VITA_IP), ip[0] ? ip : tr(S_NO_WIFI));
    text_center(cx, 280, C_TEXT, 1.3f, b);
    snprintf(b, sizeof(b), tr(S_UDP_PORT), VMON_PORT);
    text_center(cx, 320, C_TEXT, 1.3f, b);
    text_center(cx, 380, C_MUTED, 1.0f, tr(S_HINT_RUN));
    text_center(cx, 410, C_MUTED, 1.0f, tr(S_HINT_TARGET));
    text_center(cx, 510, C_MUTED, 0.9f, tr(S_HINT_KEYS));
}

/* Vista compacta: una métrica grande (valor + unidad), mini gráfica de 60 s y barra.
 * is_temp: escala 30-100 °C y colores de temperatura; si no, 0-100 %. */
static void compact_metric(int x, int y, int w, float v, float shown, int is_temp, const History *h)
{
    char b[16];
    const char *unit = is_temp ? "°C" : "%";
    unsigned int c = v < 0 ? C_MUTED : is_temp ? temp_color(v) : pct_color(v);
    float lo = is_temp ? 30 : 0, f;
    int nw, gx;

    /* número grande y unidad pegada a su línea base */
    fmtv(b, sizeof(b), "%.0f", v);
    text(x, y + 112, c, 4.2f, b);
    nw = vita2d_pgf_text_width(font, 4.2f, b);
    if (v >= 0)
        text(x + nw + 6, y + 112, c, 1.8f, unit);

    /* mini gráfica a la derecha del número */
    gx = x + 210;
    if (gx + 120 < x + w) {
        vita2d_draw_rectangle(gx, y + 22, x + w - gx, 92, C_BG);
        vita2d_draw_line(gx, y + 22 + 46, x + w, y + 22 + 46, C_TRACK);
        plot(gx, y + 22, x + w - gx, 92, h, lo, 100, is_temp ? C_LINE_TEMP : C_LINE_PCT);
    }

    /* barra: en °C muestra dónde está entre 30 y 100 */
    f = is_temp ? (v < 0 ? 0 : (v - lo) / (100 - lo) * 100) : shown;
    f = f < 0 ? 0 : f > 100 ? 100 : f;
    vita2d_draw_rectangle(x, y + 134, w, 14, C_TRACK);
    vita2d_draw_rectangle(x, y + 134, w * f / 100.0f, 14, c);
}

static void compact_panel(int y, const char *title, const char *model, const char *extra, float pct,
                          float shown, float temp, const History *hp, const History *ht)
{
    const int x = 12, w = 936, half = (w - 48) / 2;
    vita2d_draw_rectangle(x, y, w, 232, C_PANEL);
    text(x + 20, y + 36, C_TEXT, 1.4f, title);
    text_fit(x + 90, y + 36, 520, C_MUTED, 1.1f, model);
    text_right(x + w - 20, y + 36, C_TEXT, 1.1f, extra);
    compact_metric(x + 20, y + 58, half, pct, shown, 0, hp);
    vita2d_draw_line(x + w / 2, y + 66, x + w / 2, y + 206, C_TRACK);
    compact_metric(x + w / 2 + 4, y + 58, half, temp, -1, 1, ht);
}

static void draw_compact(const AppState *st)
{
    const VmonStats *s = &st->stats;
    char ram[32], vram[40], a[16], b[16];

    snprintf(ram, sizeof(ram), "RAM %s", fmtv(a, sizeof(a), "%.0f%%", s->ram));
    if (s->vramu >= 0 && s->vramt > 0)
        snprintf(vram, sizeof(vram), "VRAM %s / %s GB", fmtv(a, sizeof(a), "%.1f", s->vramu),
                 fmtv(b, sizeof(b), "%.0f", s->vramt));
    else
        snprintf(vram, sizeof(vram), "VRAM --");

    compact_panel(52, "CPU", s->cpu_name, ram, s->cpu, st->d_cpu, s->ctemp, &st->h_cpu, &st->h_ctemp);
    compact_panel(296, "GPU", s->gpu_name, vram, s->gpu, st->d_gpu, s->gtemp, &st->h_gpu, &st->h_gtemp);
}

static void draw_debug(const AppState *st, const char *ip)
{
    char b[128];
    const char *p = st->last_line;
    int y = SCREEN_H - 150, len = (int)strlen(p);
    vita2d_draw_rectangle(0, y - 26, SCREEN_W, SCREEN_H - y + 26, RGBA8(0, 0, 0, 220));
    snprintf(b, sizeof(b), "%s: %s   %s: %d   IP Vita: %s", tr(S_ORIGIN), st->from_ip[0] ? st->from_ip : "--",
             tr(S_PPS), st->pps, ip[0] ? ip : "--");
    text(12, y, RGBA8(0xFF, 0xFF, 0x80, 0xFF), 0.9f, b);
    /* la línea cruda, cortada en renglones de 110 caracteres */
    while (len > 0 && y < SCREEN_H - 20) {
        int n = len > 110 ? 110 : len;
        y += 20;
        memcpy(b, p, n);
        b[n] = '\0';
        text(12, y, RGBA8(0xE6, 0xEA, 0xEE, 0xFF), 0.75f, b);
        p += n;
        len -= n;
    }
}

static void draw_toast(void)
{
    char b[64];
    int w;
    snprintf(b, sizeof(b), tr(S_LANGUAGE), tr(S_LANG_NAME));
    w = vita2d_pgf_text_width(font, 1.2f, b) + 48;
    vita2d_draw_rectangle((SCREEN_W - w) / 2, 440, w, 50, RGBA8(0x24, 0x2C, 0x36, 0xF0));
    text_center(SCREEN_W / 2, 474, RGBA8(0xFF, 0xFF, 0xFF, 0xFF), 1.2f, b);
}

void ui_init(void)
{
    vita2d_init();
    vita2d_set_clear_color(C_BG);
    font = vita2d_load_default_pgf();
}

void ui_draw(const AppState *st, const char *vita_ip)
{
    vita2d_start_drawing();
    vita2d_clear_screen();

    dim = 0;
    if (st->conn == CONN_WAITING) {
        draw_header(st);
        draw_waiting(st, vita_ip);
    } else {
        dim = (st->conn == CONN_LOST);
        if (st->compact) {
            draw_compact(st);
        } else {
            draw_cpu(st, 12, 52, 462);
            draw_gpu(st, 486, 52, 462);
            draw_bottom(st);
        }
        dim = 0;
        draw_header(st);
        if (st->conn == CONN_LOST) {
            vita2d_draw_rectangle(280, 236, 400, 56, RGBA8(0x5A, 0x16, 0x16, 0xF0));
            text_center(SCREEN_W / 2, 272, RGBA8(0xFF, 0xFF, 0xFF, 0xFF), 1.2f, tr(S_LOST_BANNER));
        }
    }
    if (st->debug)
        draw_debug(st, vita_ip);
    if (st->lang_toast > 0)
        draw_toast();

    vita2d_end_drawing();
    vita2d_wait_rendering_done();
    vita2d_swap_buffers();
}

void ui_fini(void)
{
    vita2d_wait_rendering_done();
    vita2d_free_pgf(font);
    vita2d_fini();
}
