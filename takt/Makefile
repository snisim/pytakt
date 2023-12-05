PYFILES = __init__.py chord.py constants.py context.py effector.py \
event.py frameutils.py interpolator.py m21conv.py midiio.py mml.py \
pianoroll.py pitch.py pytakt.py sc.py scale.py score.py smf.py text.py \
timemap.py utils.py gm/__init__.py gm/drums.py

pycodestyle:
	pycodestyle $(PYFILES) | fgrep -v -x -f pycodestyle.expect || true
	python3 tests/len79.py $(PYFILES)

test:
	run.sh pytest

longtest:
	env TEST_ALL=1 run.sh pytest

html:
	cd ..; make html

src:
	cd src; make

sdist:
	cd ..; python3 setup.py sdist
