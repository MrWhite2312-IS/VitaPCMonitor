#include "lang.h"

#include <string.h>

/* Los textos van en UTF-8: la fuente PGF de la Vita dibuja acentos, ñ, ç, ß y °. */
static const char *const strings[LANG_COUNT][S_COUNT] = {
    [LANG_ES] = {
        [S_LANG_NAME] = "Español",
        [S_LANGUAGE] = "Idioma: %s",
        [S_CONNECTED] = "Conectado",
        [S_LOST] = "Sin señal",
        [S_WAITING] = "Esperando",
        [S_LOST_BANNER] = "Sin señal del PC",
        [S_WAITING_DATA] = "Esperando datos...",
        [S_NET_ERROR] = "Error de red:",
        [S_NOTICE] = "Aviso:",
        [S_VITA_IP] = "IP de la Vita: %s",
        [S_NO_WIFI] = "(sin WiFi)",
        [S_UDP_PORT] = "Puerto UDP: %d",
        [S_HINT_RUN] = "En el PC abre VitaMon.exe y pulsa Iniciar",
        [S_HINT_TARGET] = "Si no llega nada, escribe la IP de la Vita en VitaMon",
        [S_HINT_KEYS] = "START: salir    SELECT: idioma",
        [S_NO_THREAD_DATA] = "sin datos por hilo",
        [S_NET] = "RED",
        [S_UP] = "Subida %s KB/s",
        [S_DOWN] = "Bajada %s KB/s",
        [S_DISK] = "DISCO",
        [S_ORIGIN] = "Origen",
        [S_PPS] = "Paquetes/s",
    },
    [LANG_EN] = {
        [S_LANG_NAME] = "English",
        [S_LANGUAGE] = "Language: %s",
        [S_CONNECTED] = "Connected",
        [S_LOST] = "No signal",
        [S_WAITING] = "Waiting",
        [S_LOST_BANNER] = "No signal from PC",
        [S_WAITING_DATA] = "Waiting for data...",
        [S_NET_ERROR] = "Network error:",
        [S_NOTICE] = "Notice:",
        [S_VITA_IP] = "Vita IP: %s",
        [S_NO_WIFI] = "(no WiFi)",
        [S_UDP_PORT] = "UDP port: %d",
        [S_HINT_RUN] = "On the PC, open VitaMon.exe and press Start",
        [S_HINT_TARGET] = "If nothing arrives, enter the Vita IP in VitaMon",
        [S_HINT_KEYS] = "START: quit    SELECT: language",
        [S_NO_THREAD_DATA] = "no per-thread data",
        [S_NET] = "NET",
        [S_UP] = "Up %s KB/s",
        [S_DOWN] = "Down %s KB/s",
        [S_DISK] = "DISK",
        [S_ORIGIN] = "Source",
        [S_PPS] = "Packets/s",
    },
    [LANG_PT] = {
        [S_LANG_NAME] = "Português",
        [S_LANGUAGE] = "Idioma: %s",
        [S_CONNECTED] = "Conectado",
        [S_LOST] = "Sem sinal",
        [S_WAITING] = "Aguardando",
        [S_LOST_BANNER] = "Sem sinal do PC",
        [S_WAITING_DATA] = "Aguardando dados...",
        [S_NET_ERROR] = "Erro de rede:",
        [S_NOTICE] = "Aviso:",
        [S_VITA_IP] = "IP do Vita: %s",
        [S_NO_WIFI] = "(sem WiFi)",
        [S_UDP_PORT] = "Porta UDP: %d",
        [S_HINT_RUN] = "No PC, abra o VitaMon.exe e clique em Iniciar",
        [S_HINT_TARGET] = "Se nada chegar, digite o IP do Vita no VitaMon",
        [S_HINT_KEYS] = "START: sair    SELECT: idioma",
        [S_NO_THREAD_DATA] = "sem dados por thread",
        [S_NET] = "REDE",
        [S_UP] = "Envio %s KB/s",
        [S_DOWN] = "Receb. %s KB/s",
        [S_DISK] = "DISCO",
        [S_ORIGIN] = "Origem",
        [S_PPS] = "Pacotes/s",
    },
    [LANG_FR] = {
        [S_LANG_NAME] = "Français",
        [S_LANGUAGE] = "Langue : %s",
        [S_CONNECTED] = "Connecté",
        [S_LOST] = "Pas de signal",
        [S_WAITING] = "En attente",
        [S_LOST_BANNER] = "Pas de signal du PC",
        [S_WAITING_DATA] = "En attente de données...",
        [S_NET_ERROR] = "Erreur réseau :",
        [S_NOTICE] = "Avis :",
        [S_VITA_IP] = "IP de la Vita : %s",
        [S_NO_WIFI] = "(pas de WiFi)",
        [S_UDP_PORT] = "Port UDP : %d",
        [S_HINT_RUN] = "Sur le PC, ouvrez VitaMon.exe et cliquez sur Démarrer",
        [S_HINT_TARGET] = "Si rien n'arrive, saisissez l'IP de la Vita dans VitaMon",
        [S_HINT_KEYS] = "START : quitter    SELECT : langue",
        [S_NO_THREAD_DATA] = "pas de données par thread",
        [S_NET] = "RÉSEAU",
        [S_UP] = "Envoi %s Ko/s",
        [S_DOWN] = "Récep. %s Ko/s",
        [S_DISK] = "DISQUE",
        [S_ORIGIN] = "Source",
        [S_PPS] = "Paquets/s",
    },
    [LANG_DE] = {
        [S_LANG_NAME] = "Deutsch",
        [S_LANGUAGE] = "Sprache: %s",
        [S_CONNECTED] = "Verbunden",
        [S_LOST] = "Kein Signal",
        [S_WAITING] = "Warte",
        [S_LOST_BANNER] = "Kein Signal vom PC",
        [S_WAITING_DATA] = "Warte auf Daten...",
        [S_NET_ERROR] = "Netzwerkfehler:",
        [S_NOTICE] = "Hinweis:",
        [S_VITA_IP] = "Vita-IP: %s",
        [S_NO_WIFI] = "(kein WLAN)",
        [S_UDP_PORT] = "UDP-Port: %d",
        [S_HINT_RUN] = "Am PC VitaMon.exe öffnen und auf Starten klicken",
        [S_HINT_TARGET] = "Kommt nichts an, die Vita-IP in VitaMon eintragen",
        [S_HINT_KEYS] = "START: Beenden    SELECT: Sprache",
        [S_NO_THREAD_DATA] = "keine Daten pro Thread",
        [S_NET] = "NETZ",
        [S_UP] = "Hoch %s KB/s",
        [S_DOWN] = "Runter %s KB/s",
        [S_DISK] = "DISK",
        [S_ORIGIN] = "Quelle",
        [S_PPS] = "Pakete/s",
    },
    [LANG_IT] = {
        [S_LANG_NAME] = "Italiano",
        [S_LANGUAGE] = "Lingua: %s",
        [S_CONNECTED] = "Connesso",
        [S_LOST] = "Nessun segnale",
        [S_WAITING] = "In attesa",
        [S_LOST_BANNER] = "Nessun segnale dal PC",
        [S_WAITING_DATA] = "In attesa di dati...",
        [S_NET_ERROR] = "Errore di rete:",
        [S_NOTICE] = "Avviso:",
        [S_VITA_IP] = "IP della Vita: %s",
        [S_NO_WIFI] = "(niente WiFi)",
        [S_UDP_PORT] = "Porta UDP: %d",
        [S_HINT_RUN] = "Sul PC apri VitaMon.exe e premi Avvia",
        [S_HINT_TARGET] = "Se non arriva nulla, inserisci l'IP della Vita in VitaMon",
        [S_HINT_KEYS] = "START: esci    SELECT: lingua",
        [S_NO_THREAD_DATA] = "nessun dato per thread",
        [S_NET] = "RETE",
        [S_UP] = "Invio %s KB/s",
        [S_DOWN] = "Ricez. %s KB/s",
        [S_DISK] = "DISCO",
        [S_ORIGIN] = "Origine",
        [S_PPS] = "Pacchetti/s",
    },
};

static Lang cur = LANG_EN;

const char *tr_in(Lang l, StrId id)
{
    const char *s;
    if ((unsigned)l >= LANG_COUNT || (unsigned)id >= S_COUNT)
        return "";
    s = strings[l][id];
    if (!s) /* texto que falta: inglés */
        s = strings[LANG_EN][id];
    return s ? s : "";
}

int lang_missing(Lang l)
{
    int id, n = 0;
    for (id = 0; id < S_COUNT; id++)
        n += strings[l][id] == NULL;
    return n;
}

const char *tr(StrId id)
{
    return tr_in(cur, id);
}

Lang lang_get(void)
{
    return cur;
}

void lang_set(Lang l)
{
    if ((unsigned)l < LANG_COUNT)
        cur = l;
}

#ifdef __vita__

#include <psp2/apputil.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/system_param.h>

#define CFG_DIR "ux0:data/VitaMon"
#define CFG_FILE CFG_DIR "/lang.txt"

/* Código de 2 letras que se guarda en el archivo de configuración. */
static const char *const codes[LANG_COUNT] = {"es", "en", "pt", "fr", "de", "it"};

static int apputil_up;

static Lang from_system(void)
{
    int sys = -1;
    if (!apputil_up || sceAppUtilSystemParamGetInt(SCE_SYSTEM_PARAM_ID_LANG, &sys) < 0)
        return LANG_EN;
    switch (sys) {
    case SCE_SYSTEM_PARAM_LANG_SPANISH:
        return LANG_ES;
    case SCE_SYSTEM_PARAM_LANG_PORTUGUESE_PT:
    case SCE_SYSTEM_PARAM_LANG_PORTUGUESE_BR:
        return LANG_PT;
    case SCE_SYSTEM_PARAM_LANG_FRENCH:
        return LANG_FR;
    case SCE_SYSTEM_PARAM_LANG_GERMAN:
        return LANG_DE;
    case SCE_SYSTEM_PARAM_LANG_ITALIAN:
        return LANG_IT;
    default:
        return LANG_EN;
    }
}

static int load_saved(Lang *out)
{
    char buf[8] = {0};
    int i, n, fd = sceIoOpen(CFG_FILE, SCE_O_RDONLY, 0);
    if (fd < 0)
        return -1;
    n = sceIoRead(fd, buf, sizeof(buf) - 1);
    sceIoClose(fd);
    if (n < 2)
        return -1;
    for (i = 0; i < LANG_COUNT; i++) {
        if (!strncmp(buf, codes[i], 2)) {
            *out = (Lang)i;
            return 0;
        }
    }
    return -1;
}

static void save(void)
{
    int fd;
    sceIoMkdir(CFG_DIR, 0777); /* falla si ya existe: da igual */
    fd = sceIoOpen(CFG_FILE, SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC, 0777);
    if (fd < 0)
        return;
    sceIoWrite(fd, codes[cur], 2);
    sceIoClose(fd);
}

void lang_init(void)
{
    SceAppUtilInitParam init;
    SceAppUtilBootParam boot;
    Lang l;
    memset(&init, 0, sizeof(init));
    memset(&boot, 0, sizeof(boot));
    apputil_up = sceAppUtilInit(&init, &boot) >= 0;
    cur = load_saved(&l) == 0 ? l : from_system();
}

void lang_fini(void)
{
    if (apputil_up)
        sceAppUtilShutdown();
    apputil_up = 0;
}

#else /* host (tests): sin sistema ni archivo */

static void save(void) {}
void lang_init(void) {}
void lang_fini(void) {}

#endif

void lang_next(void)
{
    cur = (Lang)((cur + 1) % LANG_COUNT);
    save();
}
