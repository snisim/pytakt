#ifndef _Takt_Defs_
#define _Takt_Defs_

#include <vector>

#define C_SUSTAIN  64
#define C_ALL_SOUND_OFF  120
#define C_ALL_NOTES_OFF  123
#define M_TEMPO  0x51

#define ALL_TRACKS  (-1)

/* dummy device for testing without actual MIDI device */
#define DEV_DUMMY  (-1)

/* special device for loop-back */
#define DEV_LOOPBACK  (-2)

typedef std::vector<unsigned char>  message_t;

#endif
