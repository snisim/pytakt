#if (defined(_MSC_VER) || defined(__CYGWIN__)) && !defined(USE_GENERIC)
#include "sysdepWin.cpp"
#elif defined(__APPLE__) && !defined(USE_GENERIC)
#include "sysdepMacOSX.cpp"
#elif defined(__linux__) && !defined(USE_GENERIC)
#include "sysdepLinux.cpp"
#else
#include "sysdepGeneric.cpp"
#endif

