import inspect


def outerglobals():
    return inspect.currentframe().f_back.f_back.f_globals


def outerlocals():
    return inspect.currentframe().f_back.f_back.f_locals


if __name__ == '__main__':
    def test2():
        b = 2
        print(outerglobals())
        print(outerlocals())
        assert (outerlocals()['a'] == 1)
        assert ('b' not in outerlocals())

    def test1():
        a = 1
        test2()

    test1()
    print("test ok")
