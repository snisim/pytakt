/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 */

/* Copyright (C) 2025  Satoshi Nishimura */


#include "_cstddefs.h"
#include "midiout.h"
#include "midiin.h"
#define PY_SSIZE_T_CLEAN
#include <Python.h>

using namespace Takt;
using namespace std;

static void shutdown();
static void takt_sigint_handler(int);

static void initialize()
{
    SysDep::initialize(PyOS_setsig);
    MidiIn::startup();
    MidiOut::startup();
    Py_AtExit(shutdown);
}

static void shutdown()
{
    // printf("shutdown pytakt.midiio\n");
    MidiOut::shutdown();
    MidiIn::shutdown();
}

static void stop_all()
{
    MidiOut::stopAll();
    MidiIn::interrupt();
}

namespace Takt {
    int midimsg_size(int status)
    {
	static int  table[8] = {3, 3, 3, 3, 2, 2, 3, 0};
	int  len;
	
	if( (len = table[(status >> 4) & 7]) ) {
	    return len;
	} else switch(status) {
	case 0xf0:
	    return 0;       /* exclusive */
	case 0xf1:
	case 0xf3:
	    return 2;
	case 0xf2:
	    return 3;
	default:
	    return 1;
	}
    }
}

static PyObject* conv_to_pystr(const char *str)
{
#if PY_MAJOR_VERSION < 3
    return PyString_FromString(str);
#else
    PyObject *s = PyUnicode_FromString(str);
    if( !s ) {
	PyErr_Clear();
	s = PyUnicode_FromFormat("%s", str);
    }
    return s;
#endif
}
	
static PyObject* takt_output_devices(PyObject *self)
{
    int numDevs = SysDep::midiout_get_num_devs();
    PyObject *result = PyList_New(numDevs);
    if( !result ) return NULL;

    for( int i = 0; i < numDevs; i++ ) {
	PyObject *s = conv_to_pystr(SysDep::midiout_get_dev_name(i).c_str());
	if( !s ) {
	    Py_DECREF(result);
	    return NULL;
	}
	PyList_SetItem(result, i, s);
    }

    return result;
}

static PyObject* takt_input_devices(PyObject *self)
{
    int numDevs = SysDep::midiin_get_num_devs();
    PyObject *result = PyList_New(numDevs);
    if( !result ) return NULL;

    for( int i = 0; i < numDevs; i++ ) {
	PyObject *s = conv_to_pystr(SysDep::midiin_get_dev_name(i).c_str());
	if( !s ) {
	    Py_DECREF(result);
	    return NULL;
	}
	PyList_SetItem(result, i, s);
    }

    return result;
}

static PyObject* takt_default_output_device(PyObject *self)
{
    return Py_BuildValue("i", SysDep::midiout_get_default_dev());
}

static PyObject* takt_default_input_device(PyObject *self)
{
    return Py_BuildValue("i", SysDep::midiin_get_default_dev());
}

static PyObject* takt_open_output_device(PyObject *self, PyObject *args)
{
    int devNum;
    if( !PyArg_ParseTuple(args, "i", &devNum) ) return NULL;
    bool err = MidiOut::openDevice(devNum);
    if( err ) {
	PyErr_SetString(PyExc_RuntimeError, "device open failed");
	return NULL;
    }
    return Py_BuildValue("");
}

static PyObject* takt_close_output_device(PyObject *self, PyObject *args)
{
    int devNum;
    if( !PyArg_ParseTuple(args, "i", &devNum) ) return NULL;
    MidiOut::closeDevice(devNum);
    return Py_BuildValue("");
}

static PyObject* takt_open_input_device(PyObject *self, PyObject *args)
{
    int devNum;
    if( !PyArg_ParseTuple(args, "i", &devNum) ) return NULL;
    bool err = MidiIn::openDevice(devNum);
    if( err ) {
	PyErr_SetString(PyExc_RuntimeError, "device open failed");
	return NULL;
    }
    return Py_BuildValue("");
}

static PyObject* takt_close_input_device(PyObject *self, PyObject *args)
{
    int devNum;
    if( !PyArg_ParseTuple(args, "i", &devNum) ) return NULL;
    MidiIn::closeDevice(devNum);
    return Py_BuildValue("");
}

static PyObject* takt_is_opened_output_device(PyObject *self, PyObject *args)
{
    int devNum;
    if( !PyArg_ParseTuple(args, "i", &devNum) ) return NULL;
    return PyBool_FromLong(MidiOut::isOpenedDevice(devNum));
}

static PyObject* takt_is_opened_input_device(PyObject *self, PyObject *args)
{
    int devNum;
    if( !PyArg_ParseTuple(args, "i", &devNum) ) return NULL;
    return PyBool_FromLong(MidiIn::isOpenedDevice(devNum));
}

// queue_message(devNum, time, tk, msg)
static PyObject* takt_queue_message(PyObject *self, PyObject *args)
{
    int devNum, tk;
    double ticks;
    Py_buffer buf;
#if PY_MAJOR_VERSION < 3
    const char *fmt = "idis*";
#else
    const char *fmt = "idiy*";
#endif
    if( !PyArg_ParseTuple(args, fmt, &devNum, &ticks, &tk, &buf) )
	return NULL;

    message_t msg((unsigned char*)buf.buf, (unsigned char*)buf.buf + buf.len);
    PyBuffer_Release(&buf);
    if( devNum != DEV_LOOPBACK &&
	!(msg.size() > 0 &&
	  ((msg[0] >= 0x80 && msg[0] < 0xf0 && 
	    msg.size() == midimsg_size(msg[0])) || 
	   msg[0] == 0xf0 || msg[0] == 0xff)) ) {
	PyErr_SetString(PyExc_ValueError, "invalid MIDI (or meta) message");
	return NULL;
    }
    bool err = MidiOut::queueMessage(devNum, ticks, tk, msg);
    if( err ) {
	PyErr_SetString(PyExc_RuntimeError, "device is not opened");
	return NULL;
    }
    return Py_BuildValue("");
}

static PyObject* takt_current_time(PyObject *self)
{
    return Py_BuildValue("d", MidiOut::getCurrentTime());
}

static PyObject* takt_current_tempo(PyObject *self)
{
    return Py_BuildValue("d", MidiOut::getCurrentTempo());
}

static PyObject* takt_current_tempo_scale(PyObject *self)
{
    return Py_BuildValue("d", MidiOut::getTempoScale());
}

static PyObject* takt_set_tempo_scale(PyObject *self, PyObject *args)
{
    double scale;
    if( !PyArg_ParseTuple(args, "d", &scale) ) return NULL;
    MidiOut::setTempoScale(scale);
    return Py_BuildValue("");
}

static PyObject* takt_stop(PyObject *self)
{
    stop_all();
    return Py_BuildValue("");
}

static PyObject* takt_recv_ready(PyObject *self)
{
    return Py_BuildValue("O", MidiIn::receiveReady() ? Py_True : Py_False);
}

static PyObject* takt_recv_message(PyObject *self)
{
    int devNum, tk;
    double ticks;
    message_t msg;

    Py_BEGIN_ALLOW_THREADS
    MidiIn::receiveMessage(devNum, ticks, tk, msg);
    Py_END_ALLOW_THREADS

#if PY_MAJOR_VERSION < 3
    return Py_BuildValue("(idiN)", devNum, ticks, tk,
			 PyByteArray_FromStringAndSize(
			     msg.empty() ? NULL : (char*)&msg[0], msg.size()));
#else
    return Py_BuildValue("(idiy#)", devNum, ticks, tk,
			 msg.empty() ? NULL : &msg[0], msg.size());
#endif
}

static PyObject* takt_interrupt_recv_message(PyObject *self)
{
    MidiIn::interrupt();
    return Py_BuildValue("");
}

// _cancel_messages(devNum, tk)
static PyObject* takt_cancel_messages(PyObject *self, PyObject *args)
{
    int devNum, tk;
    if( !PyArg_ParseTuple(args, "ii", &devNum, &tk) ) return NULL;
    MidiOut::cancelMessages(devNum, tk);
    return Py_BuildValue("");
}

static PyObject* takt_set_retrigger(PyObject *self, PyObject *args)
{
    int enable;
    if( !PyArg_ParseTuple(args, "p", &enable) ) return NULL;
    MidiOut::setRetrigger(enable);
    return Py_BuildValue("");
}


static PyMethodDef cmidiio_methods[] = {
    { "output_devices", (PyCFunction)takt_output_devices, METH_NOARGS },
    { "input_devices", (PyCFunction)takt_input_devices, METH_NOARGS },
    { "default_output_device", (PyCFunction)takt_default_output_device, METH_NOARGS }, 
    { "default_input_device", (PyCFunction)takt_default_input_device, METH_NOARGS }, 
    { "_open_output_device", takt_open_output_device, METH_VARARGS },
    { "_close_output_device", takt_close_output_device, METH_VARARGS }, 
    { "_open_input_device", takt_open_input_device, METH_VARARGS },
    { "_close_input_device", takt_close_input_device, METH_VARARGS }, 
    { "_is_opened_output_device", takt_is_opened_output_device, METH_VARARGS },
    { "_is_opened_input_device", takt_is_opened_input_device, METH_VARARGS },
    { "queue_message", takt_queue_message, METH_VARARGS }, 
    { "current_time", (PyCFunction)takt_current_time, METH_NOARGS },
    { "current_tempo", (PyCFunction)takt_current_tempo, METH_NOARGS },
    { "current_tempo_scale", (PyCFunction)takt_current_tempo_scale, METH_NOARGS },
    { "set_tempo_scale", takt_set_tempo_scale, METH_VARARGS },
    { "stop", (PyCFunction)takt_stop, METH_NOARGS },
    { "recv_ready", (PyCFunction)takt_recv_ready, METH_NOARGS },
    { "recv_message", (PyCFunction)takt_recv_message, METH_NOARGS },
    { "_interrupt_recv_message", (PyCFunction)takt_interrupt_recv_message, METH_NOARGS },
    { "cancel_messages", takt_cancel_messages, METH_VARARGS },
    { "set_retrigger", takt_set_retrigger, METH_VARARGS },
    { NULL, NULL, 0, NULL }
};

extern "C" {
static struct PyModuleDef cmidiio_definition = {
    PyModuleDef_HEAD_INIT, "cmidiio", NULL, -1, cmidiio_methods
};

#if defined(_MSC_VER) && !defined(HAVE_DECLSPEC_DLL)
_declspec(dllexport)
#endif
PyMODINIT_FUNC
PyInit_cmidiio(void)
{
    initialize();
    return PyModule_Create(&cmidiio_definition);
}
}
