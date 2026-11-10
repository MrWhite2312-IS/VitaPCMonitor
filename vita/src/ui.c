#include "ui.h"

#include <stdio.h>
#include <string.h>

#include <psp2/rtc.h>
#include <vita2d.h>

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
    text(x + 70, y + 30, C_MUTED, 1.0f, model);
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
    panel_head(x, y, w, "CPU", "Ryzen 5 5600G", st->d_cpu, s->cpu, s->ctemp);
    if (n > 0) {
        int gap = 4, cw = (w - 32 - gap * (n - 1)) / n, top = y + 86, h = 60;
        for (i = 0; i < n; i++) {
            float f = st->d_cores[i] < 0 ? 0 : st->d_cores[i] > 100 ? 100 : st->d_cores[i];
            int bx = x + 16 + i * (cw + gap), fh = (int)(h * f / 100.0f);
            vita2d_draw_rectangle(bx, top, cw, h, C_TRACK);
            vita2d_draw_rectangle(bx, top + h - fh, cw, fh, pct_color(f));
        }
    } else {
        text(x + 16, y + 120, C_MUTED, 0.9f, "sin datos por hilo");
    }
    graph(x + 16, y + 160, w - 32, 158, &st->h_cpu, &st->h_ctemp);
}

static void draw_gpu(const AppState *st, int x, int y, int w)
{
    const VmonStats *s = &st->stats;
    char b[64], u[16], t[16];
    panel_head(x, y, w, "GPU", "RTX 3050", st->d_gpu, s->gpu, s->gtemp);
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
    vita2d_draw_rectangle(12, 394, 936, 138, C_PANEL);

    text(28, 432, C_TEXT, 1.1f, "RAM");
    bar(100, 412, 460, 26, st->d_ram);
    snprintf(b, sizeof(b), "%s / %s GB (%s)", fmtv(u, sizeof(u), "%.1f", s->ramu),
             fmtv(t, sizeof(t), "%.1f", s->ramt), fmtv(p, sizeof(p), "%.0f%%", s->ram));
    text(580, 432, C_TEXT, 1.1f, b);

    text(28, 494, C_TEXT, 1.1f, "RED");
    snprintf(b, sizeof(b), "Subida %s KB/s", fmtv(u, sizeof(u), "%.0f", s->up));
    text(100, 494, C_TEXT, 1.0f, b);
    snprintf(b, sizeof(b), "Bajada %s KB/s", fmtv(u, sizeof(u), "%.0f", s->down));
    text(330, 494, C_TEXT, 1.0f, b);
    text(580, 494, C_TEXT, 1.1f, "DISCO");
    text(670, 494, s->disk < 0 ? C_MUTED : pct_color(s->disk), 1.1f, fmtv(b, sizeof(b), "%.0f%%", s->disk));
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
        label = "Conectado";
        c = C_GREEN;
    } else if (st->conn == CONN_LOST) {
        label = "Sin señal";
        c = RGBA8(0xE8, 0x48, 0x48, 0xFF);
    } else {
        label = "Esperando";
        c = C_AMBER;
    }
    tx = SCREEN_W - 100 - vita2d_pgf_text_width(font, 1.0f, label);
    vita2d_draw_fill_circle(tx - 14, 23, 6, c);
    text(tx, 30, c, 1.0f, label);
}

static void draw_waiting(const AppState *st, const char *ip)
{
    char b[96];
    int cx = SCREEN_W / 2;
    text_center(cx, 170, C_TEXT, 2.0f, "Esperando datos...");
    if (st->net_error) {
        snprintf(b, sizeof(b), "Error de red: 0x%08X", (unsigned int)st->net_error);
        text_center(cx, 240, C_RED, 1.2f, b);
    }
    snprintf(b, sizeof(b), "IP de la Vita: %s", ip[0] ? ip : "(sin WiFi)");
    text_center(cx, 280, C_TEXT, 1.3f, b);
    snprintf(b, sizeof(b), "Puerto UDP: %d", VMON_PORT);
    text_center(cx, 320, C_TEXT, 1.3f, b);
    text_center(cx, 380, C_MUTED, 1.0f, "En el PC ejecuta:  python vitamon_server.py");
    text_center(cx, 410, C_MUTED, 1.0f, "Si no llega nada, usa  --target <IP de la Vita>");
    text_center(cx, 510, C_MUTED, 0.9f, "START: salir");
}

static void draw_compact(const AppState *st)
{
    const VmonStats *s = &st->stats;
    static const char *labels[4] = {"CPU %", "CPU °C", "GPU %", "GPU °C"};
    float vals[4];
    int i;
    vals[0] = s->cpu;
    vals[1] = s->ctemp;
    vals[2] = s->gpu;
    vals[3] = s->gtemp;
    for (i = 0; i < 4; i++) {
        char b[16];
        int x = 12 + (i % 2) * 474, y = 52 + (i / 2) * 244;
        unsigned int c = vals[i] < 0 ? C_MUTED : (i % 2) ? temp_color(vals[i]) : pct_color(vals[i]);
        vita2d_draw_rectangle(x, y, 462, 232, C_PANEL);
        text(x + 16, y + 34, C_MUTED, 1.2f, labels[i]);
        text_center(x + 231, y + 175, c, 5.0f, fmtv(b, sizeof(b), "%.0f", vals[i]));
    }
}

static void draw_debug(const AppState *st, const char *ip)
{
    char b[128];
    const char *p = st->last_line;
    int y = SCREEN_H - 150, len = (int)strlen(p);
    vita2d_draw_rectangle(0, y - 26, SCREEN_W, SCREEN_H - y + 26, RGBA8(0, 0, 0, 220));
    snprintf(b, sizeof(b), "Origen: %s   Paquetes/s: %d   IP Vita: %s", st->from_ip[0] ? st->from_ip : "--",
             st->pps, ip[0] ? ip : "--");
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
            text_center(SCREEN_W / 2, 272, RGBA8(0xFF, 0xFF, 0xFF, 0xFF), 1.2f, "Sin señal del PC");
        }
    }
    if (st->debug)
        draw_debug(st, vita_ip);

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
