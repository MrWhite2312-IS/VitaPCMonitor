/* Test del parser en el host:
 *   gcc -std=c11 -Wall -Wextra -I../src ../src/protocol.c test_protocol.c -o test_protocol && ./test_protocol
 * Con un argumento, solo parsea esa línea (exit 0 si es válida). Lo usa server/test_server_line.py.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "protocol.h"

static int failures = 0;
#define CHECK(cond)                                                       \
    do {                                                                  \
        if (!(cond)) {                                                    \
            printf("FALLA %s:%d: %s\n", __FILE__, __LINE__, #cond);       \
            failures++;                                                   \
        }                                                                 \
    } while (0)
#define FEQ(a, b) (fabs((double)(a) - (double)(b)) < 1e-3)

static void test_valid(void)
{
    VmonStats s;
    const char *line =
        "VMON1;host=DESKTOP-PC;cpu=23.4;cores=12,30,8,5,40,22,11,9,3,7,15,20;ctemp=54.0;"
        "ram=55.1;ramu=8.8;ramt=16.0;gpu=12;gtemp=60;vramu=1.2;vramt=8.0;gclk=1500;"
        "up=123.4;down=456.7;disk=40.2;ts=1731258000\r\n";
    CHECK(vmon_parse(line, &s) == 0);
    CHECK(!strcmp(s.host, "DESKTOP-PC"));
    CHECK(FEQ(s.cpu, 23.4));
    CHECK(s.ncores == 12);
    CHECK(FEQ(s.cores[0], 12) && FEQ(s.cores[11], 20));
    CHECK(FEQ(s.ctemp, 54.0));
    CHECK(FEQ(s.ram, 55.1) && FEQ(s.ramu, 8.8) && FEQ(s.ramt, 16.0));
    CHECK(FEQ(s.gpu, 12) && FEQ(s.gtemp, 60) && FEQ(s.vramu, 1.2) && FEQ(s.vramt, 8.0));
    CHECK(FEQ(s.gclk, 1500));
    CHECK(FEQ(s.up, 123.4) && FEQ(s.down, 456.7) && FEQ(s.disk, 40.2));
    CHECK(s.ts == 1731258000.0);
}

static void test_names(void)
{
    VmonStats s;
    CHECK(vmon_parse("VMON1;host=PC;cpun=Ryzen 5 5600G;gpun=RTX 3050;cpu=1", &s) == 0);
    CHECK(!strcmp(s.cpu_name, "Ryzen 5 5600G") && !strcmp(s.gpu_name, "RTX 3050"));
    CHECK(vmon_parse("VMON1;host=PC;cpu=1", &s) == 0); /* servidor viejo: sin nombres */
    CHECK(s.cpu_name[0] == '\0' && s.gpu_name[0] == '\0');
    CHECK(s.fps == -1.0f); /* servidor viejo: sin FPS */
    CHECK(vmon_parse("VMON1;cpu=1;fps=143.6", &s) == 0);
    CHECK(FEQ(s.fps, 143.6));
}

static void test_minus_one(void)
{
    VmonStats s;
    CHECK(vmon_parse("VMON1;host=X;cpu=10;ctemp=-1;gpu=-1;gtemp=-1", &s) == 0);
    CHECK(FEQ(s.cpu, 10));
    CHECK(s.ctemp == -1.0f && s.gpu == -1.0f && s.gtemp == -1.0f);
    CHECK(s.ram == -1.0f); /* ausente => -1 */
}

static void test_unknown_keys(void)
{
    VmonStats s;
    CHECK(vmon_parse("VMON1;foo=bar;cpu=5;fan=1200;sinigual;ram=7", &s) == 0);
    CHECK(FEQ(s.cpu, 5) && FEQ(s.ram, 7));
}

static void test_bad_prefix(void)
{
    VmonStats s;
    vmon_stats_reset(&s);
    s.cpu = 99;
    CHECK(vmon_parse("VMON2;cpu=5", &s) != 0);
    CHECK(vmon_parse("vmon1;cpu=5", &s) != 0);
    CHECK(vmon_parse("VMON1", &s) != 0);
    CHECK(vmon_parse("", &s) != 0);
    CHECK(vmon_parse(NULL, &s) != 0);
    CHECK(vmon_parse("hola VMON1;cpu=5", &s) != 0);
    CHECK(s.cpu == 99); /* no se toca si es inválida */
}

static void test_truncated(void)
{
    VmonStats s;
    CHECK(vmon_parse("VMON1;host=PC;cpu=23.4;cores=12,3", &s) == 0);
    CHECK(s.ncores == 2);
    CHECK(vmon_parse("VMON1;host=PC;cpu=", &s) == 0);
    CHECK(s.cpu == -1.0f);
    CHECK(vmon_parse("VMON1;host=PC;cp", &s) == 0);
    CHECK(vmon_parse("VMON1;cpu=2x", &s) == 0);
    CHECK(s.cpu == -1.0f);

    /* línea demasiado larga => inválida */
    {
        char big[VMON_MAX_LINE + 10];
        memset(big, 'a', sizeof(big));
        memcpy(big, "VMON1;", 6);
        big[sizeof(big) - 1] = '\0';
        CHECK(vmon_parse(big, &s) != 0);
    }
}

static void test_cores(void)
{
    VmonStats s;
    char line[512] = "VMON1;cores=";
    int i;
    CHECK(vmon_parse("VMON1;cores=;cpu=1", &s) == 0);
    CHECK(s.ncores == 0 && FEQ(s.cpu, 1));
    CHECK(vmon_parse("VMON1;cpu=1", &s) == 0);
    CHECK(s.ncores == 0);
    for (i = 0; i < 40; i++)
        strcat(line, i ? ",1" : "1");
    CHECK(vmon_parse(line, &s) == 0);
    CHECK(s.ncores == VMON_MAX_CORES);
}

static void test_long_host(void)
{
    VmonStats s;
    char line[256] = "VMON1;host=";
    int i;
    for (i = 0; i < 100; i++)
        strcat(line, "H");
    CHECK(vmon_parse(line, &s) == 0);
    CHECK(strlen(s.host) == VMON_HOST_LEN - 1);
}

int main(int argc, char **argv)
{
    if (argc > 1) {
        VmonStats s;
        int r = vmon_parse(argv[1], &s);
        printf("%s host=%s cpu=%.1f ncores=%d ram=%.1f gpu=%.1f\n", r ? "INVALIDA" : "OK", s.host, s.cpu,
               s.ncores, s.ram, s.gpu);
        return r ? 1 : 0;
    }
    test_valid();
    test_names();
    test_minus_one();
    test_unknown_keys();
    test_bad_prefix();
    test_truncated();
    test_cores();
    test_long_host();
    if (failures) {
        printf("%d fallas\n", failures);
        return 1;
    }
    printf("Todos los tests pasaron\n");
    return 0;
}
