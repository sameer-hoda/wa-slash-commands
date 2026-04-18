
#line 1 "cgo-builtin-prolog"
#include <stddef.h>

/* Define intgo when compiling with GCC.  */
typedef ptrdiff_t intgo;

#define GO_CGO_GOSTRING_TYPEDEF
typedef struct { const char *p; intgo n; } _GoString_;
typedef struct { char *p; intgo n; intgo c; } _GoBytes_;
_GoString_ GoString(char *p);
_GoString_ GoStringN(char *p, int l);
_GoBytes_ GoBytes(void *p, int n);
char *CString(_GoString_);
void *CBytes(_GoBytes_);
void *_CMalloc(size_t);

__attribute__ ((unused))
static size_t _GoStringLen(_GoString_ s) { return (size_t)s.n; }

__attribute__ ((unused))
static const char *_GoStringPtr(_GoString_ s) { return s.p; }
#line 8 "/Users/sameerhoda/go/pkg/mod/github.com/mattn/go-sqlite3@v1.14.32/error.go"

#ifndef USE_LIBSQLITE3
#include "sqlite3-binding.h"
#else
#include <sqlite3.h>
#endif

#line 1 "cgo-generated-wrapper"
#line 1 "cgo-dwarf-inference"
__typeof__(GoString) *__cgo__0;
__typeof__(int) *__cgo__1;
__typeof__(sqlite3_errstr) *__cgo__2;
long long __cgodebug_ints[] = {
	0,
	0,
	0,
	1
};
double __cgodebug_floats[] = {
	0,
	0,
	0,
	1
};
