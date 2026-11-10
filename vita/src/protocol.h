#ifndef VMON_PROTOCOL_H
#define VMON_PROTOCOL_H

/* Protocolo VMON1: una línea ASCII "VMON1;clave=valor;...". Sin dependencias de VitaSDK. */

#define VMON_PREFIX "VMON1;"
#define VMON_MAX_LINE 1024
#define VMON_MAX_CORES 32
#define VMON_HOST_LEN 64
#define VMON_NAME_LEN 48

typedef struct {
    char host[VMON_HOST_LEN];
    char cpu_name[VMON_NAME_LEN], gpu_name[VMON_NAME_LEN]; /* "" si el servidor no los manda */
    float cpu;
    float cores[VMON_MAX_CORES];
    int ncores;
    float ctemp;
    float ram, ramu, ramt;
    float gpu, gtemp, vramu, vramt, gclk;
    float up, down;
    float disk;
    float fps; /* FPS del juego en primer plano (RivaTuner / LHM); -1 sin juego */
    double ts;
} VmonStats;

/* Todos los valores en -1 ("no disponible"), host vacío, ncores 0. */
void vmon_stats_reset(VmonStats *s);

/* Devuelve 0 si la línea es válida y rellena *out; -1 si no (y *out queda intacto). */
int vmon_parse(const char *line, VmonStats *out);

#endif
