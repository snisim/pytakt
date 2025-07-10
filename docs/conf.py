# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
sys.path.insert(0, os.path.abspath('../'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'pytakt'
copyright = '2025, Satoshi Nishimura'
author = 'Satoshi Nishimura'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
add_module_names = False


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme = 'alabaster'
# html_theme = 'default'
html_theme = 'nature'
html_static_path = ['_static']
# html_style = 'overrides.css'

autodoc_member_order = 'bysource'

def process_docstring(app, what, name, obj, options, lines):
    if what == 'class':
        for i, line in enumerate(lines):
            if line.startswith('.. attribute::'):
                lines.insert(i, '')
                lines.insert(i, '.. rubric:: Attributes')
                break
        for i, line in enumerate(lines):
            if line.startswith(":param"):
                lines.insert(i, '')
                lines.insert(i, '.. rubric:: Constructor')
                break
        lines.append('|')
        # lines.append('.. rubric:: Methods/Constants')

def setup(app):
    app.connect('autodoc-process-docstring', process_docstring)

os.environ['__SPHINX_AUTODOC__'] = '1'
