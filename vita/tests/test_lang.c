/* Test de las traducciones en el host:
 *   gcc -std=c11 -Wall -Wextra -I../src ../src/lang.c test_lang.c -o test_lang && ./test_lang
 * Comprueba que no falte ningún texto y que los % de formato coincidan con el inglés.
 */
#include <stdio.h>
#include <string.h>

#include "lang.h"

/* Secuencia de especificadores de formato, p. ej. "%s%d". */
static void specs(const char *s, char *out, size_t cap)
{
    size_t n = 0;
    for (; *s && n + 2 < cap; s++) {
        if (*s != '%')
            continue;
        s++;
        if (*s == '%')
            continue;
        out[n++] = '%';
        out[n++] = *s;
    }
    out[n] = '\0';
}

int main(void)
{
    int l, id, failures = 0;
    for (l = 0; l < LANG_COUNT; l++) {
        if (lang_missing((Lang)l)) {
            printf("FALTAN %d textos en idioma %d\n", lang_missing((Lang)l), l);
            failures++;
        }
        for (id = 0; id < S_COUNT; id++) {
            char a[16], b[16];
            const char *s = tr_in((Lang)l, (StrId)id);
            const char *en = tr_in(LANG_EN, (StrId)id);
            if (!s[0]) {
                printf("FALTA idioma %d texto %d\n", l, id);
                failures++;
            }
            specs(s, a, sizeof(a));
            specs(en, b, sizeof(b));
            if (strcmp(a, b)) {
                printf("FORMATO idioma %d texto %d: \"%s\" vs \"%s\"\n", l, id, s, en);
                failures++;
            }
        }
    }
    lang_set(LANG_IT);
    lang_next();
    if (lang_get() != LANG_ES) {
        printf("lang_next no da la vuelta\n");
        failures++;
    }
    if (!failures)
        printf("OK: %d idiomas x %d textos\n", LANG_COUNT, S_COUNT);
    return failures != 0;
}
