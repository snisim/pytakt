DEST = ../cmidiio.so
INCLUDE = -I/usr/include/python3.8
LIBS = -lasound
CXXFLAGS += -fPIC -shared $(INCLUDE)
OBJS = cmidiio.o midiout.o midiin.o sysdep.o

$(DEST): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $(DEST) $(OBJS) $(LIBS)

clean:
	rm -f $(DEST) $(OBJS)

# DO NOT DELETE

cmidiio.o: _cstddefs.h midiout.h sysdep.h sysdepLinux.h sysdepGeneric.h
cmidiio.o: defs.h midiin.h
midiout.o: _cstddefs.h midiout.h sysdep.h sysdepLinux.h sysdepGeneric.h
midiout.o: defs.h midiin.h notemap.h
midiin.o: _cstddefs.h midiin.h sysdep.h sysdepLinux.h sysdepGeneric.h defs.h
midiin.o: midiout.h
sysdep.o: sysdepLinux.cpp sysdepGeneric.cpp sysdep.h _cstddefs.h
sysdep.o: sysdepLinux.h sysdepGeneric.h takterror.h
