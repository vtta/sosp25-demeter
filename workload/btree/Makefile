program = BTree
source = btree1.c
obj = $(source:.c=.o)
objomp = $(source:.c=.o-omp)

# Standard Flags
CFLAGS := -std=gnu99 -Wall -O3

# compiler
CC = gcc

.PHONY: all clean
all: bench_btree_st bench_btree_mt

$(program): $(obj) Makefile
	$(CC) $(CFLAGS) $(obj) -o $@ $(LDFLAGS)

libbtree.a: $(obj) Makefile
	ar rcs $@ $(obj)

libbtreeomp.a: $(objomp) Makefile
	ar rcs $@ $(objomp)

%.o: %.c Makefile
	$(CC) $(CFLAGS) -c $< -o $@

%.o-omp: %.c Makefile
	$(CC) $(CFLAGS) -fopenmp -c $< -o $@

clean:
	rm -rf $(program) $(obj)
	rm -f *.a
	rm -f *.o-omp
	rm -rf bench_btree_st bench_btree_mt

SRC = main.c btree1.c
LIBS = -lrt -ldl -lnuma -lpthread -lm
bench_btree_mt: $(SRC) config.h
	$(CC) $(INCLUDES) $(CFLAGS) $(SRC) -o $@ $(LIBS) -fopenmp
bench_btree_st: $(SRC) config.h
	$(CC) $(INCLUDES) $(CFLAGS) $(SRC) -o $@ $(LIBS)
