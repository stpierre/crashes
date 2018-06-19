#!/usr/bin/env python

import pip
import setuptools

setuptools.setup(
    name="crashes",
    version="0.1.0",
    description="Bicycle crash analysis (Lincoln, NE)",
    author="Chris St. Pierre",
    author_email="chris.a.st.pierre@gmail.com",
    packages=["crashes", "crashes.commands"],
    # TODO: restore requirements bits
    entry_points={"console_scripts": "crashes = crashes.cli:main"})
