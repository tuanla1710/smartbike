#include "bike_ctrl.h"

#include <stdio.h>
#include <string.h>

void host_exec(const char *text, bike_reply_t *out);

static void strip(char *line)
{
    size_t n = strlen(line);
    while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r' || line[n - 1] == ' ')) {
        line[--n] = '\0';
    }
    char *start = line;
    while (*start == ' ') {
        start++;
    }
    if (start != line) {
        memmove(line, start, strlen(start) + 1);
    }
}

static int self_test(void)
{
    if (bike_elapsed(10u, 0xfffffff0u) != 26u) {
        fprintf(stderr, "elapsed wrap failed\n");
        return 1;
    }
    uint8_t flag = 1;
    if (bike_crc8(&flag, 1) == 0) {
        fprintf(stderr, "crc8 failed\n");
        return 1;
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "--self-test") == 0) {
        return self_test();
    }
    bike_plant_t plant;
    bike_plant_init(&plant);
    bike_setup(&plant, false);
    setvbuf(stdout, NULL, _IOLBF, 0);
    char line[192];
    while (fgets(line, sizeof line, stdin) != NULL) {
        strip(line);
        bike_reply_t reply;
        reply.count = 0;
        if (line[0] != '\0' && line[0] != '#') {
            host_exec(line, &reply);
        }
        for (int i = 0; i < reply.count; i++) {
            printf("%s\n", reply.text[i]);
        }
        printf(".\n");
    }
    return 0;
}
