#ifndef VMON_NET_H
#define VMON_NET_H

#include "protocol.h"

/* No usar puertos >= 49152: la Vita rechaza el bind con EACCES (0x8041010D). */
#define VMON_PORT 10555

/* 0 si todo bien; negativo (código SCE) si falla. */
int net_init(void);
/* Relee la IP de la Vita (cadena vacía si no hay WiFi). */
void net_refresh_ip(void);
const char *net_ip(void);

/* Lee todos los datagramas pendientes sin bloquear.
 * Devuelve cuántos datagramas válidos llegaron; si >0, *out, line y from_ip tienen el último válido. */
int net_poll(VmonStats *out, char *line, int line_cap, char *from_ip, int from_cap);

/* Primer error de init como "paso: 0x...", o "" si no hubo. */
const char *net_error_text(void);

void net_fini(void);

#endif
