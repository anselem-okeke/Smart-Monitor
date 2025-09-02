// zombie simulator
// ./zombie_simulator 7 //here is how to run the simulator
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>

int main(int argc, char **argv) {
    int n = (argc > 1) ? atoi(argv[1]) : 1;   // how many zombies to make
    printf("Parent PID: %d — creating %d zombie(s)\n", getpid(), n);
    for (int i = 0; i < n; i++) {
        pid_t pid = fork();
        if (pid == 0) {
            _exit(0);          // child exits immediately → becomes zombie
        }
    }
    sleep(600);                 // keep parent alive (don’t call wait)
    return 0;
}
