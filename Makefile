PYTHON=python3
TMPFILE=/tmp/pytakt_tmp.py

html:
	sphinx-build docs docs/_build

html-ja:
	make conv_docstr_ja
	sphinx-build _ja/docs _ja/docs/_build

sdist:
	make conv_docstr_en
	(cd _en; $(PYTHON) setup.py sdist)
	mkdir -p dist
	mv -i _en/dist/*.tar.gz dist

sdist-ja:
	make conv_docstr_ja
	(cd _ja; $(PYTHON) setup.py sdist)
	mkdir -p dist
	mv -i _ja/dist/*.tar.gz dist/$$(basename _ja/dist/*.tar.gz .tar.gz)-ja.tar.gz

conv_docstr_en:
	rm -rf _en
	mkdir _en
	tar cXf .tarignore - . | (cd _en; tar xf -)
	for i in $$(find _en -name \*.py -print); do \
		$(PYTHON) conv_docstr.py --lang en $$i > $(TMPFILE); \
		touch -r $$i $(TMPFILE); \
		mv -f $(TMPFILE) $$i; \
	done

conv_docstr_ja:
	rm -rf _ja
	mkdir _ja
	tar cXf .tarignore - . | (cd _ja; tar xf -)
	for i in $$(find _ja -name \*.py -print); do \
		$(PYTHON) conv_docstr.py --lang ja $$i > $(TMPFILE); \
		touch -r $$i $(TMPFILE); \
		mv -f $(TMPFILE) $$i; \
	done
	mv _ja/docs/conf.py.ja _ja/docs/conf.py
	mv _ja/docs/takt.rst.ja _ja/docs/takt.rst

clean:
	rm -rf _en _ja
