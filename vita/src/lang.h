#ifndef VMON_LANG_H
#define VMON_LANG_H

/* Idiomas de la interfaz. El orden es el que recorre SELECT. */
typedef enum { LANG_ES, LANG_EN, LANG_PT, LANG_FR, LANG_DE, LANG_IT, LANG_COUNT } Lang;

typedef enum {
    S_LANG_NAME,     /* nombre del idioma en sí mismo */
    S_LANGUAGE,      /* "Idioma: %s" */
    S_CONNECTED,
    S_LOST,          /* estado corto en la cabecera */
    S_WAITING,
    S_LOST_BANNER,   /* cartel grande "Sin señal del PC" */
    S_WAITING_DATA,
    S_NET_ERROR,
    S_NOTICE,
    S_VITA_IP,       /* "%s" = IP */
    S_NO_WIFI,
    S_UDP_PORT,      /* "%d" = puerto */
    S_HINT_RUN,
    S_HINT_TARGET,
    S_HINT_KEYS,
    S_NO_THREAD_DATA,
    S_NET,
    S_UP,            /* "%s" = KB/s */
    S_DOWN,          /* "%s" = KB/s */
    S_DISK,
    S_ORIGIN,
    S_PPS,
    S_COUNT
} StrId;

/* Carga el idioma guardado; si no hay, usa el del sistema (o inglés). */
void lang_init(void);
void lang_fini(void);

Lang lang_get(void);
void lang_set(Lang l);
/* Pasa al siguiente idioma y lo guarda en ux0:data/VitaMon/lang.txt. */
void lang_next(void);

const char *tr(StrId id);
/* Texto de un idioma concreto (para tests). */
const char *tr_in(Lang l, StrId id);
/* Cuántos textos le faltan a un idioma (para tests). */
int lang_missing(Lang l);

#endif
