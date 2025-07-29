#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <errno.h>

void usage(const char *prog)
{
	fprintf(stderr, "Usage: %s <file> <command> [args...]\n", prog);
	exit(EXIT_FAILURE);
}

int main(int argc, char *argv[])
{
	if (argc < 3) {
		usage(argv[0]);
	}

	const char *file = argv[1];
	char *cmd = argv[2];
	char **args = &argv[2];

	// Open the file for reading
	int fd = open(file, O_RDONLY);
	if (fd < 0) {
		fprintf(stderr, "Error: Failed to open file '%s': %s\n", file,
			strerror(errno));
		exit(EXIT_FAILURE);
	}

	// Redirect stdin to the file
	if (dup2(fd, STDIN_FILENO) < 0) {
		fprintf(stderr, "Error: Failed to redirect stdin: %s\n",
			strerror(errno));
		close(fd); // Clean up before exiting
		exit(EXIT_FAILURE);
	}

	// Execute the command
	if (execvp(cmd, args) < 0) {
		fprintf(stderr, "Error: Failed to execute command '%s': %s\n",
			cmd, strerror(errno));
		exit(EXIT_FAILURE);
	}

	// This line should never be reached
	return EXIT_SUCCESS;
}
