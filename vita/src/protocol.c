#include "protocol.h"

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

void vmon_stats_reset(VmonStats *s)
{
    memset(s, 0, sizeof(*s));
    s->cpu = s->ctemp = s->ram = s->ramu = s->ramt = -1.0f;
    s->gpu = s->gtemp = s->vramu = s->vramt = s->gclk = -1.0f;
    s->up = s->down = s->disk = -1.0f;
    s->ts = -1.0;
}

/* Número vacío o con basura => -1 (no disponible). */
static float parse_num(const char *v)
{
    char *end;
    float f;
    if (!*v)
        return -1.0f;
    f = strtof(v, &end);
    return (end == v || *end) ? -1.0f : f;
}

static void parse_cores(char *v, VmonStats *s)
{
    s->ncores = 0;
    while (*v && s->ncores < VMON_MAX_CORES) {
        char *comma = strchr(v, ',');
        if (comma)
            *comma = '\0';
        s->cores[s->ncores++] = parse_num(v);
        if (!comma)
            break;
        v = comma + 1;
    }
}

int vmon_parse(const char *line, VmonStats *out)
{
    char buf[VMON_MAX_LINE];
    size_t len;
    char *p;
    VmonStats s;

    if (!line || strncmp(line, VMON_PREFIX, sizeof(VMON_PREFIX) - 1) != 0)
        return -1;
    len = strlen(line);
    if (len >= sizeof(buf))
        return -1;
    memcpy(buf, line, len + 1);
    while (len && (buf[len - 1] == '\n' || buf[len - 1] == '\r'))
        buf[--len] = '\0';

    vmon_stats_reset(&s);
    p = buf + sizeof(VMON_PREFIX) - 1;
    while (*p) {
        char *semi = strchr(p, ';');
        char *eq;
        if (semi)
            *semi = '\0';
        eq = strchr(p, '=');
        if (eq) {
            char *k = p, *v = eq + 1;
            *eq = '\0';
            if (!strcmp(k, "host")) {
                strncpy(s.host, v, VMON_HOST_LEN - 1);
            } else if (!strcmp(k, "cores")) {
                parse_cores(v, &s);
            } else if (!strcmp(k, "ts")) {
                s.ts = strtod(v, NULL);
            } else {
                static const struct { const char *k; size_t off; } keys[] = {
                    {"cpu", offsetof(VmonStats, cpu)},     {"ctemp", offsetof(VmonStats, ctemp)},
                    {"ram", offsetof(VmonStats, ram)},     {"ramu", offsetof(VmonStats, ramu)},
                    {"ramt", offsetof(VmonStats, ramt)},   {"gpu", offsetof(VmonStats, gpu)},
                    {"gtemp", offsetof(VmonStats, gtemp)}, {"vramu", offsetof(VmonStats, vramu)},
                    {"vramt", offsetof(VmonStats, vramt)}, {"gclk", offsetof(VmonStats, gclk)},
                    {"up", offsetof(VmonStats, up)},       {"down", offsetof(VmonStats, down)},
                    {"disk", offsetof(VmonStats, disk)},
                };
                size_t i;
                for (i = 0; i < sizeof(keys) / sizeof(keys[0]); i++) {
                    if (!strcmp(k, keys[i].k)) {
                        *(float *)((char *)&s + keys[i].off) = parse_num(v);
                        break;
                    }
                }
                /* claves desconocidas: se ignoran */
            }
        }
        if (!semi)
            break;
        p = semi + 1;
    }

    *out = s;
    return 0;
}
