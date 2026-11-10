#ifndef VMON_UI_H
#define VMON_UI_H

#include "protocol.h"

#define HIST_LEN 60

typedef struct {
    float v[HIST_LEN];
    int head, count; /* head = próxima posición a escribir */
} History;

typedef enum { CONN_WAITING, CONN_OK, CONN_LOST } ConnState;

typedef struct {
    VmonStats stats;
    ConnState conn;
    int compact, debug;
    int net_error;            /* != 0 si falló net_init */
    History h_cpu, h_gpu, h_ctemp, h_gtemp;
    /* valores mostrados en las barras (lerp hacia stats) */
    float d_cpu, d_gpu, d_ram, d_cores[VMON_MAX_CORES];
    char last_line[VMON_MAX_LINE];
    char from_ip[16];
    int pps;
    int lang_toast;           /* != 0 mientras se ve el aviso de idioma */
    int batt;                 /* batería de la Vita en %, -1 en PS TV o si no se puede leer */
    int charging;
} AppState;

void hist_push(History *h, float v);

void ui_init(void);
void ui_draw(const AppState *st, const char *vita_ip);
void ui_fini(void);

#endif
