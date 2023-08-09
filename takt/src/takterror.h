#ifndef _Takt_Error_
#define _Takt_Error_

namespace Takt {
struct Error {
    static void no_memory() {
	fprintf(stderr, "Not enough memory\n");
	exit(1);
    }
};
}

#endif
