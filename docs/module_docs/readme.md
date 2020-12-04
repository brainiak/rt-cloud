This README explains how the automated code documentation building system works.

## Initial Setup
The `sphinx-quickstart` command (more info
[here](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/sphinx-quickstart.html#quickstart))
sets up the boilerplate files to fill out.

The `conf.py` file is the primary way of controlling/modifying the building
process.

## Rebuilding
`sphinx-build` with type/source/destination arguments builds the docs. The
AutoAPI extension is configured with the source directory (rtCommon), and it
automatically discovers modules to document during the `sphinx-build` process.

Example: `sphinx-build -b html module_docs build`
