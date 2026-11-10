#include "net.h"

#include <stdio.h>
#include <string.h>

#include <psp2/net/net.h>
#include <psp2/net/netctl.h>
#include <psp2/sysmodule.h>

static char net_mem[1024 * 1024];
static int sock = -1;
static int net_up, netctl_up, sysmod_up;
static char ip[16];
static char err[96];

const char *net_error_text(void)
{
    return err;
}

/* Guarda el primer error (paso + código) para mostrarlo en pantalla. */
static void note(const char *step, int r)
{
    if (!err[0])
        snprintf(err, sizeof(err), "%s: 0x%08X", step, (unsigned int)r);
}

int net_init(void)
{
    SceNetInitParam param;
    SceNetSockaddrIn addr;
    int r;

    /* sysmodule, sceNetInit y sceNetCtlInit pueden fallar si otro ya los inicializó:
     * se anota el error y se sigue; lo que manda es si el socket abre. */
    if ((r = sceSysmoduleLoadModule(SCE_SYSMODULE_NET)) < 0)
        note("sceSysmoduleLoadModule", r);
    else
        sysmod_up = 1;

    param.memory = net_mem;
    param.size = sizeof(net_mem);
    param.flags = 0;
    r = sceNetInit(&param);
    if (r >= 0)
        net_up = 1;
    else if (r != (int)SCE_NET_ERROR_EBUSY) /* EBUSY = ya inicializado */
        note("sceNetInit", r);

    if ((r = sceNetCtlInit()) < 0)
        note("sceNetCtlInit", r);
    else
        netctl_up = 1;
    net_refresh_ip();

    r = sceNetSocket("vitamon", SCE_NET_AF_INET, SCE_NET_SOCK_DGRAM, SCE_NET_IPPROTO_UDP);
    if (r < 0) {
        err[0] = '\0';
        note("sceNetSocket", r);
        return r;
    }
    sock = r;

    memset(&addr, 0, sizeof(addr));
    addr.sin_len = sizeof(addr);
    addr.sin_family = SCE_NET_AF_INET;
    addr.sin_addr.s_addr = sceNetHtonl(SCE_NET_INADDR_ANY);
    addr.sin_port = sceNetHtons(VMON_PORT);
    if ((r = sceNetBind(sock, (SceNetSockaddr *)&addr, sizeof(addr))) < 0) {
        err[0] = '\0';
        note("sceNetBind", r);
        sceNetSocketClose(sock);
        sock = -1;
        return r;
    }
    return 0; /* puede haber un aviso en err aunque todo funcione */
}

void net_refresh_ip(void)
{
    SceNetCtlInfo info;
    if (netctl_up && sceNetCtlInetGetInfo(SCE_NETCTL_INFO_GET_IP_ADDRESS, &info) >= 0) {
        strncpy(ip, info.ip_address, sizeof(ip) - 1);
        ip[sizeof(ip) - 1] = '\0';
    } else {
        ip[0] = '\0';
    }
}

const char *net_ip(void)
{
    return ip;
}

int net_poll(VmonStats *out, char *line, int line_cap, char *from_ip, int from_cap)
{
    char buf[VMON_MAX_LINE];
    int valid = 0;

    if (sock < 0)
        return 0;
    for (;;) {
        SceNetSockaddrIn from;
        unsigned int fromlen = sizeof(from);
        int n = sceNetRecvfrom(sock, buf, sizeof(buf) - 1, SCE_NET_MSG_DONTWAIT, (SceNetSockaddr *)&from,
                               &fromlen);
        if (n < 0) /* would block o error: no hay más */
            break;
        buf[n] = '\0';
        if (vmon_parse(buf, out) == 0) {
            valid++;
            strncpy(line, buf, line_cap - 1);
            line[line_cap - 1] = '\0';
            sceNetInetNtop(SCE_NET_AF_INET, &from.sin_addr, from_ip, from_cap);
        }
    }
    return valid;
}

void net_fini(void)
{
    if (sock >= 0)
        sceNetSocketClose(sock);
    sock = -1;
    if (netctl_up)
        sceNetCtlTerm();
    if (net_up)
        sceNetTerm();
    if (sysmod_up)
        sceSysmoduleUnloadModule(SCE_SYSMODULE_NET);
    netctl_up = net_up = sysmod_up = 0;
}
