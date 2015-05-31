#!/usr/bin/env python

import setuptools

setuptools.setup(
    name="crashes",
    version="0.1.0",
    description="Bicycle crash analysis (Lincoln, NE)",
    author="Chris St. Pierre",
    author_email="chris.a.st.pierre@gmail.com",
    packages=["crashes",
              "crashes.cmd"],
    install_requires=open("requirements.txt").readlines(),
    entry_points={
        "console_scripts": "crashes = crashes.cli:main"})
