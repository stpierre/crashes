#!/usr/bin/env python

import pip
from pip import req
import setuptools

setuptools.setup(
    name="crashes",
    version="0.1.0",
    description="Bicycle crash analysis (Lincoln, NE)",
    author="Chris St. Pierre",
    author_email="chris.a.st.pierre@gmail.com",
    packages=["crashes",
              "crashes.cmd"],
    install_requires=[
        str(r.req)
        for r in req.parse_requirements("requirements.txt",
                                        session=pip.download.PipSession())],
    entry_points={
        "console_scripts": "crashes = crashes.cli:main"})
